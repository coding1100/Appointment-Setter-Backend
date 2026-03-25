"""
Public chatbot embed runtime endpoints.
"""

from html import escape
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from app.api.v1.schemas.chatbot_agent import ChatbotEmbedConfigResponse, ChatbotEmbedStreamRequest
from app.chatbot_agents.service import chatbot_agent_service
from app.core.config import CHATBOT_DEV_ALLOW_ANY_ORIGIN, ENVIRONMENT
from app.core.security import SecurityService

router = APIRouter(prefix="/chatbot-embed", tags=["chatbot-embed"])


def _allow_origin_bypass() -> bool:
    return str(ENVIRONMENT).strip().lower() == "development" and CHATBOT_DEV_ALLOW_ANY_ORIGIN


def _normalize_origin(value: Optional[str]) -> str:
    if not value:
        return ""
    raw = value.strip().rstrip("/")
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return raw


def _resolve_request_origin(
    origin_header: Optional[str], embed_origin: Optional[str], referer_header: Optional[str] = None
) -> str:
    return _normalize_origin(embed_origin) or _normalize_origin(origin_header) or _normalize_origin(referer_header)


async def _enforce_public_rate_limit(request: Request, operation: str, limit: int, window_seconds: int) -> None:
    client_ip = request.client.host if request.client else "unknown"
    security_service = SecurityService()
    await security_service.enforce_rate_limit(client_ip, limit=limit, window_seconds=window_seconds, operation=operation)


def _raise_embed_error(exc: ValueError) -> None:
    message = str(exc)
    if "temporarily disabled" in message:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message) from exc
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message) from exc


@router.get("/config", response_model=ChatbotEmbedConfigResponse)
async def get_chatbot_embed_config(
    request: Request,
    token: str = Query(...),
    origin: Optional[str] = Header(None, alias="Origin"),
    embed_origin: Optional[str] = Query(None),
):
    await _enforce_public_rate_limit(request, operation="chatbot_embed_config", limit=60, window_seconds=60)

    request_origin = _resolve_request_origin(origin, embed_origin)
    if not request_origin and not _allow_origin_bypass():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Origin is required")
    if not request_origin:
        request_origin = "dev://no-origin"

    try:
        config = await chatbot_agent_service.get_public_embed_config(token=token, request_origin=request_origin)
    except ValueError as exc:
        _raise_embed_error(exc)
    return ChatbotEmbedConfigResponse(**config)


@router.post("/stream")
async def stream_chatbot_embed_response(
    request: Request,
    payload: ChatbotEmbedStreamRequest,
    token: str = Query(...),
    origin: Optional[str] = Header(None, alias="Origin"),
    embed_origin: Optional[str] = Query(None),
):
    await _enforce_public_rate_limit(request, operation="chatbot_embed_stream", limit=20, window_seconds=60)

    request_origin = _resolve_request_origin(origin, embed_origin)
    if not request_origin and not _allow_origin_bypass():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Origin is required")
    if not request_origin:
        request_origin = "dev://no-origin"

    try:
        config = await chatbot_agent_service.get_public_embed_config(token=token, request_origin=request_origin)
    except ValueError as exc:
        _raise_embed_error(exc)

    chatbot = await chatbot_agent_service.get_chatbot_agent(config["chatbot_id"])
    if not chatbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot not found")

    request_id = request.headers.get("x-request-id")
    client_ip = request.client.host if request.client else "unknown"
    history_payload = [entry.dict() for entry in payload.history]
    stream = chatbot_agent_service.stream_chat_reply(
        chatbot=chatbot,
        message=payload.message,
        history=history_payload,
        request_id=request_id,
        client_ip=client_ip,
    )

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(stream, media_type="text/event-stream", headers=headers)


@router.get("/loader.js", include_in_schema=False)
async def get_chatbot_embed_loader(
    request: Request,
    token: str = Query(..., min_length=1),
    embed_origin: Optional[str] = Query(None),
    origin: Optional[str] = Header(None, alias="Origin"),
    referer: Optional[str] = Header(None, alias="Referer"),
):
    await _enforce_public_rate_limit(request, operation="chatbot_embed_loader", limit=120, window_seconds=60)

    # Browsers often omit Origin for script GET requests but include Referer.
    request_origin = _resolve_request_origin(origin, embed_origin, referer)
    if not request_origin and not _allow_origin_bypass():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Origin is required")
    if not request_origin:
        request_origin = "dev://no-origin"

    try:
        config = await chatbot_agent_service.get_public_embed_config(token=token, request_origin=request_origin)
    except ValueError as exc:
        _raise_embed_error(exc)
    chatbot = await chatbot_agent_service.get_chatbot_agent(config["chatbot_id"])
    if not chatbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot not found")

    launcher = chatbot["launcher_config"]
    position = launcher["position"]
    label = launcher["button_label"]
    accent = launcher["accent_color"]
    panel_url = str(request.url_for("get_chatbot_embed_panel")) + f"?token={escape(token, quote=True)}"
    left = "20px" if position == "bottom-left" else "auto"
    right = "20px" if position == "bottom-right" else "auto"

    script = f"""
(function () {{
  if (window.__asChatbotLauncherLoaded) return;
  window.__asChatbotLauncherLoaded = true;

  var root = document.createElement("div");
  root.id = "as-chatbot-launcher-root";
  root.style.position = "fixed";
  root.style.bottom = "20px";
  root.style.left = "{left}";
  root.style.right = "{right}";
  root.style.zIndex = "999999";
  root.style.fontFamily = "Arial, sans-serif";

  var button = document.createElement("button");
  button.type = "button";
  button.textContent = {label!r};
  button.style.border = "0";
  button.style.borderRadius = "999px";
  button.style.padding = "12px 16px";
  button.style.background = {accent!r};
  button.style.color = "#fff";
  button.style.fontWeight = "600";
  button.style.cursor = "pointer";
  button.style.boxShadow = "0 8px 24px rgba(2, 6, 23, 0.25)";

  var panel = document.createElement("div");
  panel.style.width = "380px";
  panel.style.maxWidth = "calc(100vw - 24px)";
  panel.style.height = "560px";
  panel.style.maxHeight = "70vh";
  panel.style.marginBottom = "10px";
  panel.style.background = "#fff";
  panel.style.border = "1px solid #d1d5db";
  panel.style.borderRadius = "14px";
  panel.style.overflow = "hidden";
  panel.style.boxShadow = "0 16px 40px rgba(2, 6, 23, 0.26)";
  panel.style.display = "none";

  var iframe = document.createElement("iframe");
  iframe.src = {panel_url!r};
  iframe.title = "Chatbot Panel";
  iframe.style.width = "100%";
  iframe.style.height = "100%";
  iframe.style.border = "0";
  iframe.allow = "microphone";
  iframe.loading = "lazy";
  iframe.referrerPolicy = "strict-origin-when-cross-origin";
  panel.appendChild(iframe);

  button.addEventListener("click", function () {{
    panel.style.display = panel.style.display === "none" ? "block" : "none";
  }});

  document.addEventListener("keydown", function (event) {{
    if (event.key === "Escape") {{
      panel.style.display = "none";
    }}
  }});

  root.appendChild(panel);
  root.appendChild(button);
  document.body.appendChild(root);
}})();
""".strip()

    return Response(content=script, media_type="application/javascript")


@router.get("/panel", response_class=HTMLResponse, include_in_schema=False, name="get_chatbot_embed_panel")
async def get_chatbot_embed_panel(token: str = Query(..., min_length=1)):
    safe_token = escape(token, quote=True)
    html_content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Chatbot Panel</title>
  <style>
    :root {{
      --primary: #2563eb;
      --bg: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --border: #e2e8f0;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .panel {{
      height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    .header {{
      padding: 14px 16px;
      border-bottom: 1px solid var(--border);
      background: var(--primary);
      color: #fff;
      font-weight: 600;
    }}
    .body {{
      padding: 14px 16px;
      overflow: hidden;
      flex: 1;
      background: var(--bg);
      color: var(--text);
    }}
    .messages {{
      height: 100%;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .message {{
      max-width: 92%;
      width: fit-content;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: #f8fafc;
      line-height: 1.35;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .message.user {{
      margin-left: auto;
      background: #e0f2fe;
      border-color: #bae6fd;
    }}
    .message.assistant {{
      margin-right: auto;
    }}
    .message.error {{
      background: #fee2e2;
      border-color: #fecaca;
      color: #b91c1c;
    }}
    .footer {{
      padding: 12px 14px;
      border-top: 1px solid var(--border);
      display: flex;
      gap: 8px;
      align-items: flex-end;
      background: #fff;
    }}
    .composer {{
      flex: 1;
      min-height: 40px;
      max-height: 120px;
      resize: vertical;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 10px 12px;
      font: inherit;
      color: var(--text);
      outline: none;
      background: #fff;
    }}
    .composer:focus {{
      border-color: var(--primary);
      box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
    }}
    .send-btn {{
      border: 0;
      border-radius: 10px;
      padding: 10px 14px;
      background: var(--primary);
      color: #fff;
      font-weight: 600;
      cursor: pointer;
      min-width: 78px;
    }}
    .send-btn:disabled {{
      opacity: 0.55;
      cursor: not-allowed;
    }}
    .mic-btn {{
      border: 1px solid var(--border);
      border-radius: 10px;
      width: 42px;
      height: 42px;
      padding: 0;
      background: #fff;
      color: var(--text);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.15s ease;
      flex-shrink: 0;
    }}
    .mic-btn:hover:not(:disabled) {{
      border-color: var(--primary);
      box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12);
    }}
    .mic-btn:disabled {{
      opacity: 0.45;
      cursor: not-allowed;
    }}
    .mic-btn.active {{
      background: #dc2626;
      border-color: #dc2626;
      color: #fff;
      box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.18);
    }}
    .mic-icon {{
      width: 18px;
      height: 18px;
      display: block;
    }}
    .sr-only {{
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      border: 0;
    }}
    .status {{
      padding: 0 16px 10px;
      font-size: 12px;
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <div class="panel">
    <div class="header" id="chatbot-title">Loading chatbot...</div>
    <div class="body">
      <div class="messages" id="chatbot-messages"></div>
    </div>
    <div class="status" id="chatbot-status">Initializing chatbot...</div>
    <div class="footer">
      <textarea id="chatbot-input" class="composer" placeholder="Type your message..." rows="1"></textarea>
      <button id="chatbot-mic" class="mic-btn" type="button" aria-label="Start voice input" aria-pressed="false" title="Start voice input" disabled>
        <span class="sr-only">Mic</span>
        <svg class="mic-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 1 0 6 0V6a3 3 0 0 0-3-3Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
          <path d="M19 11a7 7 0 0 1-14 0" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
          <path d="M12 18v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
          <path d="M8 21h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
        </svg>
      </button>
      <button id="chatbot-send" class="send-btn" type="button">Send</button>
    </div>
  </div>
  <script src="/api-static/vendor/annyang.min.js"></script>
  <script>
    (async function () {{
      const token = "{safe_token}";
      const title = document.getElementById("chatbot-title");
      const messages = document.getElementById("chatbot-messages");
      const status = document.getElementById("chatbot-status");
      const input = document.getElementById("chatbot-input");
      const micButton = document.getElementById("chatbot-mic");
      const sendButton = document.getElementById("chatbot-send");
      let chatHistory = [];
      let isSending = false;
      let speechEnabled = false;
      let speechBlockedReason = "";
      let isListening = false;
      let speechFinalTranscript = "";
      let preListenInputValue = "";
      let recognition = null;

      const appendMessage = function (role, text, extraClass) {{
        const el = document.createElement("div");
        let className = "message " + role;
        if (extraClass) {{
          className += " " + extraClass;
        }}
        el.className = className;
        el.textContent = text || "";
        messages.appendChild(el);
        messages.scrollTop = messages.scrollHeight;
        return el;
      }};

      const setComposerDisabled = function (disabled) {{
        input.disabled = disabled;
        sendButton.disabled = disabled;
        if (micButton && !isListening) {{
          micButton.disabled = disabled || !speechEnabled;
        }}
      }};

      const isLocalhost = function () {{
        const host = window.location.hostname;
        return host === "localhost" || host === "127.0.0.1" || host === "[::1]";
      }};

      const isSpeechSecureContext = function () {{
        return window.isSecureContext || isLocalhost();
      }};

      const setReadyStatus = function () {{
        if (speechBlockedReason) {{
          status.textContent = "Ready | Voice disabled: " + speechBlockedReason;
          return;
        }}
        status.textContent = "Ready";
      }};

      const refreshMicButtonState = function () {{
        if (!micButton) {{
          return;
        }}

        micButton.classList.toggle("active", isListening);
        micButton.setAttribute("aria-pressed", isListening ? "true" : "false");
        micButton.setAttribute("aria-label", isListening ? "Stop voice input" : "Start voice input");

        if (isListening) {{
          micButton.title = "Stop voice input";
          return;
        }}

        if (speechEnabled) {{
          micButton.title = "Start voice input";
          return;
        }}

        micButton.title = speechBlockedReason ? "Voice disabled: " + speechBlockedReason : "Voice input unavailable";
      }};

      const disableSpeech = function (reason) {{
        speechEnabled = false;
        speechBlockedReason = reason || "unsupported";
        isListening = false;
        if (micButton) {{
          micButton.disabled = true;
        }}
        refreshMicButtonState();
      }};

      const initializeSpeechRecognition = function () {{
        if (!micButton) {{
          return;
        }}
        if (!isSpeechSecureContext()) {{
          disableSpeech("requires HTTPS");
          return;
        }}
        if (!window.annyang || typeof window.annyang.getSpeechRecognizer !== "function") {{
          disableSpeech("library not loaded");
          return;
        }}

        try {{
          window.annyang.init({{}}, false);
        }} catch (_error) {{
          disableSpeech("browser not supported");
          return;
        }}

        recognition = window.annyang.getSpeechRecognizer();
        if (!recognition) {{
          disableSpeech("browser not supported");
          return;
        }}

        recognition.continuous = false;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;
        recognition.lang = "en-US";

        recognition.onstart = function () {{
          isListening = true;
          refreshMicButtonState();
          status.textContent = "Listening...";
        }};

        recognition.onerror = function (event) {{
          const errorCode = event && event.error ? event.error : "unknown";
          if (errorCode === "not-allowed" || errorCode === "service-not-allowed") {{
            disableSpeech("microphone permission denied");
            status.textContent = "Voice input blocked by browser permissions.";
            return;
          }}
          status.textContent = "Voice input error: " + errorCode;
        }};

        recognition.onresult = function (event) {{
          if (!event || !event.results) {{
            return;
          }}
          let finalChunk = "";
          let interimChunk = "";
          for (let i = event.resultIndex; i < event.results.length; i += 1) {{
            const result = event.results[i];
            const transcript = result && result[0] && result[0].transcript ? result[0].transcript : "";
            if (!transcript) {{
              continue;
            }}
            if (result.isFinal) {{
              finalChunk += transcript + " ";
            }} else {{
              interimChunk += transcript;
            }}
          }}

          if (finalChunk) {{
            speechFinalTranscript += finalChunk;
          }}

          const composed = (speechFinalTranscript + interimChunk).trim();
          if (composed) {{
            input.value = composed;
          }}
        }};

        recognition.onend = function () {{
          const spokenText = (input.value || speechFinalTranscript || "").trim();
          const shouldSubmit = Boolean(spokenText) && !isSending;

          isListening = false;
          speechFinalTranscript = "";
          refreshMicButtonState();

          if (!shouldSubmit) {{
            if (!spokenText) {{
              input.value = preListenInputValue;
            }}
            setReadyStatus();
            return;
          }}

          input.value = spokenText;
          submitMessage();
        }};

        speechEnabled = true;
        speechBlockedReason = "";
        if (!isSending) {{
          micButton.disabled = false;
        }}
        refreshMicButtonState();
      }};

      const getEmbedOrigin = function () {{
        try {{
          if (document.referrer) {{
            return new URL(document.referrer).origin;
          }}
        }} catch (_error) {{
          return "";
        }}
        return "";
      }};

      if (!token) {{
        status.textContent = "Missing token.";
        setComposerDisabled(true);
        return;
      }}

      try {{
        const embedOrigin = getEmbedOrigin();
        const configUrl = new URL("./config", window.location.href);
        configUrl.searchParams.set("token", token);
        if (embedOrigin) {{
          configUrl.searchParams.set("embed_origin", embedOrigin);
        }}

        const response = await fetch(configUrl.toString(), {{
          method: "GET",
          headers: {{ "Accept": "application/json" }},
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload?.detail || "Failed to load chatbot config");
        }}

        title.textContent = payload.name || "Chatbot";
        document.documentElement.style.setProperty("--primary", payload.theme?.primary_color || "#2563eb");
        document.documentElement.style.setProperty("--bg", payload.theme?.background_color || "#ffffff");
        document.documentElement.style.setProperty("--text", payload.theme?.text_color || "#0f172a");
        messages.innerHTML = "";
        const welcomeText = payload.welcome_message || "Hello!";
        appendMessage("assistant", welcomeText, "");
        chatHistory.push({{ role: "assistant", content: welcomeText }});
        setComposerDisabled(false);
        initializeSpeechRecognition();
        setReadyStatus();
        input.focus();
      }} catch (error) {{
        messages.innerHTML = "";
        appendMessage("assistant", error?.message || "Unable to initialize chatbot.", "error");
        status.textContent = "Initialization failed";
        setComposerDisabled(true);
        return;
      }}

      const parseSseChunk = function (rawEvent) {{
        const lines = rawEvent
          .split("\\n")
          .map(function (line) {{ return line.trim(); }})
          .filter(function (line) {{ return line.indexOf("data:") === 0; }})
          .map(function (line) {{ return line.slice(5).trim(); }});
        if (!lines.length) {{
          return null;
        }}
        try {{
          return JSON.parse(lines.join("\\n"));
        }} catch (_error) {{
          return null;
        }}
      }};

      const streamAssistantReply = async function (userText) {{
        if (isSending) {{
          return;
        }}
        isSending = true;
        setComposerDisabled(true);
        status.textContent = "Generating response...";

        appendMessage("user", userText, "");
        chatHistory.push({{ role: "user", content: userText }});
        const assistantNode = appendMessage("assistant", "", "");
        let assistantText = "";

        try {{
          const embedOrigin = getEmbedOrigin();
          const streamUrl = new URL("./stream", window.location.href);
          streamUrl.searchParams.set("token", token);
          if (embedOrigin) {{
            streamUrl.searchParams.set("embed_origin", embedOrigin);
          }}

          const response = await fetch(streamUrl.toString(), {{
            method: "POST",
            headers: {{
              "Content-Type": "application/json",
              "Accept": "text/event-stream"
            }},
            body: JSON.stringify({{
              message: userText,
              history: chatHistory
            }})
          }});

          if (!response.ok || !response.body) {{
            let detail = "Unable to generate response";
            try {{
              const errorPayload = await response.json();
              if (errorPayload && errorPayload.detail) {{
                detail = errorPayload.detail;
              }}
            }} catch (_error) {{}}
            throw new Error(detail);
          }}

          const reader = response.body.getReader();
          const decoder = new TextDecoder("utf-8");
          let buffer = "";

          while (true) {{
            const readState = await reader.read();
            if (readState.done) {{
              break;
            }}
            buffer += decoder.decode(readState.value, {{ stream: true }});

            let separatorIndex = buffer.indexOf("\\n\\n");
            while (separatorIndex !== -1) {{
              const rawEvent = buffer.slice(0, separatorIndex);
              buffer = buffer.slice(separatorIndex + 2);
              separatorIndex = buffer.indexOf("\\n\\n");

              const event = parseSseChunk(rawEvent);
              if (!event) {{
                continue;
              }}

              if (event.type === "delta") {{
                assistantText += event.text || "";
                assistantNode.textContent = assistantText;
                messages.scrollTop = messages.scrollHeight;
                continue;
              }}

              if (event.type === "error") {{
                assistantNode.textContent = event.message || "Unable to generate response.";
                assistantNode.classList.add("error");
                continue;
              }}

              if (event.type === "done") {{
                if (!assistantText && event.full_text) {{
                  assistantText = event.full_text;
                  assistantNode.textContent = assistantText;
                }}
              }}
            }}
          }}
        }} catch (error) {{
          assistantNode.textContent = error?.message || "Unable to generate response.";
          assistantNode.classList.add("error");
        }} finally {{
          const cleanAssistant = (assistantText || "").trim();
          if (cleanAssistant) {{
            chatHistory.push({{ role: "assistant", content: cleanAssistant }});
          }}
          isSending = false;
          setComposerDisabled(false);
          setReadyStatus();
          input.focus();
          messages.scrollTop = messages.scrollHeight;
        }}
      }};

      const submitMessage = async function () {{
        const text = (input.value || "").trim();
        if (!text || isSending) {{
          return;
        }}
        input.value = "";
        await streamAssistantReply(text);
      }};

      sendButton.addEventListener("click", function () {{
        submitMessage();
      }});

      if (micButton) {{
        micButton.addEventListener("click", function () {{
          if (!speechEnabled || isSending || !window.annyang) {{
            return;
          }}

          if (isListening) {{
            window.annyang.abort();
            return;
          }}

          preListenInputValue = (input.value || "").trim();
          speechFinalTranscript = "";
          input.value = "";

          try {{
            window.annyang.start({{ autoRestart: false, continuous: false }});
          }} catch (_error) {{
            status.textContent = "Unable to start microphone.";
          }}
        }});
      }}

      input.addEventListener("keydown", function (event) {{
        if (event.key === "Enter" && !event.shiftKey) {{
          event.preventDefault();
          submitMessage();
        }}
      }});
    }})();
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=status.HTTP_200_OK)
