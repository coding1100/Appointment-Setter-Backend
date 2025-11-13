"""
Agent management API routes.
"""
from typing import List
from fastapi import APIRouter, HTTPException, status, Query

from app.api.v1.schemas.agent import (
    AgentCreate, AgentUpdate, AgentResponse, 
    VoiceListResponse, VoicePreviewRequest
)
from app.api.v1.services.agent import agent_service

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/tenant/{tenant_id}", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    tenant_id: str,
    agent_data: AgentCreate
):
    """
    Create a new agent for a tenant.
    
    - **tenant_id**: ID of the tenant
    - **agent_data**: Agent configuration including name, voice, phone number, etc.
    """
    try:
        agent = await agent_service.create_agent(tenant_id, agent_data)
        return AgentResponse(**agent)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create agent: {str(e)}"
        )


@router.get("/tenant/{tenant_id}", response_model=List[AgentResponse])
async def list_agents(
    tenant_id: str
):
    """
    List all agents for a tenant.
    
    - **tenant_id**: ID of the tenant
    """
    try:
        agents = await agent_service.list_agents_by_tenant(tenant_id)
        return [AgentResponse(**agent) for agent in agents]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(e)}"
        )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):
    """
    Get agent by ID.
    
    - **agent_id**: ID of the agent
    """
    try:
        agent = await agent_service.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        return AgentResponse(**agent)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent: {str(e)}"
        )


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    agent_data: AgentUpdate
):
    """
    Update an agent.
    
    - **agent_id**: ID of the agent
    - **agent_data**: Updated agent configuration
    """
    try:
        agent = await agent_service.update_agent(agent_id, agent_data)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        return AgentResponse(**agent)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update agent: {str(e)}"
        )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str):
    """
    Delete an agent.
    
    - **agent_id**: ID of the agent
    """
    try:
        success = await agent_service.delete_agent(agent_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete agent: {str(e)}"
        )


@router.post("/{agent_id}/activate")
async def activate_agent(agent_id: str):
    """
    Activate an agent.
    
    - **agent_id**: ID of the agent
    """
    try:
        success = await agent_service.activate_agent(agent_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        return {"message": "Agent activated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate agent: {str(e)}"
        )


@router.post("/{agent_id}/deactivate")
async def deactivate_agent(agent_id: str):
    """
    Deactivate an agent.
    
    - **agent_id**: ID of the agent
    """
    try:
        success = await agent_service.deactivate_agent(agent_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        return {"message": "Agent deactivated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate agent: {str(e)}"
        )


@router.get("/voices/list", response_model=VoiceListResponse)
async def list_available_voices():
    """
    Get list of available ElevenLabs voices.
    
    Returns predefined list of popular ElevenLabs voices for agent configuration.
    """
    try:
        voices = agent_service.get_available_voices()
        return VoiceListResponse(
            voices=voices,
            total=len(voices)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get voices: {str(e)}"
        )


@router.get("/voices/preview/{voice_id}")
async def get_voice_preview_url(voice_id: str):
    """
    Get the audio file URL for a voice preview.
    
    Returns the static file URL for pre-generated voice samples.
    Audio files are generated once using generate_voice_samples.py script.
    
    - **voice_id**: ElevenLabs voice ID
    
    Returns:
        - **audio_url**: URL to the MP3 audio file
        - **voice_id**: The requested voice ID
    """
    try:
        # Map voice IDs to filenames
        voice_filename_map = {
            "21m00Tcm4TlvDq8ikWAM": "rachel.mp3",
            "AZnzlk1XvdvUeBnXmlld": "domi.mp3",
            "EXAVITQu4vr4xnSDxMaL": "bella.mp3",
            "ErXwobaYiN019PkySvjV": "antoni.mp3",
            "VR6AewLTigWG4xSOukaG": "arnold.mp3",
            "pNInz6obpgDQGcFmaJgB": "adam.mp3",
            "yoZ06aMxZJJ28mfd3POQ": "sam.mp3",
            "IKne3meq5aSn9XLyUdCD": "charlie.mp3",
            "XB0fDUnXU5powFXDhCwa": "charlotte.mp3",
            "pqHfZKP75CvOlQylNhV4": "bill.mp3",
            "N2lVS1w4EtoT3dr4eOWO": "callum.mp3",
            "LcfcDJNUP1GQjkzn1xUU": "emily.mp3"
        }
        
        filename = voice_filename_map.get(voice_id)
        
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Voice ID {voice_id} not found"
            )
        
        # Check if audio file exists
        import os
        audio_path = os.path.join("app", "static", "voices", filename)
        
        if not os.path.exists(audio_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Audio file not found. Please run 'python generate_voice_samples.py' to generate voice samples."
            )
        
        # Return the static file URL
        audio_url = f"/static/voices/{filename}"
        
        return {
            "audio_url": audio_url,
            "voice_id": voice_id,
            "filename": filename
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get voice preview: {str(e)}"
        )

