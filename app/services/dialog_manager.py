"""
Dialog Manager with FSM (Finite State Machine) and LLM policy for Home Services using Supabase.
Handles conversation flow, slot filling, and confirmation.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, asdict

from app.core.prompts import prompt_map
from app.services.firebase import firebase_service

class DialogState(str, Enum):
    """Dialog states for FSM."""
    GREETING = "greeting"
    COLLECTING_INFO = "collecting_info"
    CONFIRMING = "confirming"
    BOOKING = "booking"
    ESCALATING = "escalating"
    ENDING = "ending"

class SlotStatus(str, Enum):
    """Slot collection status."""
    EMPTY = "empty"
    PARTIAL = "partial"
    COMPLETE = "complete"

@dataclass
class DialogSlot:
    """Dialog slot for information collection."""
    name: str
    value: Optional[str] = None
    status: SlotStatus = SlotStatus.EMPTY
    required: bool = True
    validation_pattern: Optional[str] = None

@dataclass
class DialogContext:
    """Dialog context for conversation management."""
    tenant_id: str
    call_id: str
    service_type: str
    current_state: DialogState
    slots: Dict[str, DialogSlot]
    conversation_history: List[Dict[str, str]]
    escalation_triggered: bool = False
    confirmation_attempts: int = 0
    max_confirmation_attempts: int = 3

class DialogManager:
    """Dialog Manager for Home Services appointment booking using Firebase."""
    
    def __init__(self):
        """Initialize dialog manager."""
        self.service_slots = {
            "Home Services": ["name", "phone", "email", "service_type", "address", "datetime", "service_details"],
            "Plumbing": ["name", "phone", "email", "service_type", "address", "datetime", "service_details"],
            "Electrician": ["name", "phone", "email", "service_type", "address", "datetime", "service_details"],
            "Painter": ["name", "phone", "email", "service_type", "address", "datetime", "service_details"],
            "Carpenter": ["name", "phone", "email", "service_type", "address", "datetime", "service_details"],
            "Maids": ["name", "phone", "email", "service_type", "address", "datetime", "service_details"]
        }
    
    async def create_dialog_context(
        self,
        tenant_id: str,
        call_id: str,
        service_type: str
    ) -> DialogContext:
        """Create a new dialog context."""
        slots = {}
        required_slots = self.service_slots.get(service_type, self.service_slots["Home Services"])
        
        for slot_name in required_slots:
            slots[slot_name] = DialogSlot(
                name=slot_name,
                required=True
            )
        
        context = DialogContext(
            tenant_id=tenant_id,
            call_id=call_id,
            service_type=service_type,
            current_state=DialogState.GREETING,
            slots=slots,
            conversation_history=[]
        )
        
        return context
    
    async def process_user_input(
        self,
        context: DialogContext,
        user_input: str
    ) -> Dict[str, Any]:
        """Process user input and return response."""
        # Add user input to conversation history
        context.conversation_history.append({
            "role": "user",
            "message": user_input,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Process based on current state
        if context.current_state == DialogState.GREETING:
            return await self._handle_greeting(context, user_input)
        elif context.current_state == DialogState.COLLECTING_INFO:
            return await self._handle_info_collection(context, user_input)
        elif context.current_state == DialogState.CONFIRMING:
            return await self._handle_confirmation(context, user_input)
        elif context.current_state == DialogState.BOOKING:
            return await self._handle_booking(context, user_input)
        elif context.current_state == DialogState.ESCALATING:
            return await self._handle_escalation(context, user_input)
        else:
            return await self._handle_ending(context, user_input)
    
    async def _handle_greeting(self, context: DialogContext, user_input: str) -> Dict[str, Any]:
        """Handle greeting state."""
        greeting_message = f"Hello! I'm your {context.service_type} appointment assistant. How can I help you today?"
        
        # Move to info collection
        context.current_state = DialogState.COLLECTING_INFO
        
        # Add assistant response to history
        context.conversation_history.append({
            "role": "assistant",
            "message": greeting_message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {
            "response": greeting_message,
            "state": context.current_state.value,
            "next_action": "collect_info"
        }
    
    async def _handle_info_collection(self, context: DialogContext, user_input: str) -> Dict[str, Any]:
        """Handle information collection state."""
        # Extract information from user input
        extracted_info = await self._extract_information(context, user_input)
        
        # Update slots with extracted information
        for slot_name, value in extracted_info.items():
            if slot_name in context.slots and value:
                context.slots[slot_name].value = value
                context.slots[slot_name].status = SlotStatus.COMPLETE
        
        # Check if all required slots are filled
        if await self._are_all_slots_complete(context):
            context.current_state = DialogState.CONFIRMING
            confirmation_message = await self._generate_confirmation_message(context)
            
            context.conversation_history.append({
                "role": "assistant",
                "message": confirmation_message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return {
                "response": confirmation_message,
                "state": context.current_state.value,
                "next_action": "confirm_appointment"
            }
        else:
            # Ask for missing information
            missing_slot = await self._get_next_missing_slot(context)
            question = await self._generate_question_for_slot(missing_slot)
            
            context.conversation_history.append({
                "role": "assistant",
                "message": question,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return {
                "response": question,
                "state": context.current_state.value,
                "next_action": "collect_info"
            }
    
    async def _handle_confirmation(self, context: DialogContext, user_input: str) -> Dict[str, Any]:
        """Handle confirmation state."""
        user_input_lower = user_input.lower().strip()
        
        if user_input_lower in ["yes", "y", "confirm", "correct", "that's right"]:
            context.current_state = DialogState.BOOKING
            booking_message = "Perfect! I'm booking your appointment now. Please hold on..."
            
            context.conversation_history.append({
                "role": "assistant",
                "message": booking_message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return {
                "response": booking_message,
                "state": context.current_state.value,
                "next_action": "book_appointment"
            }
        elif user_input_lower in ["no", "n", "incorrect", "wrong", "change"]:
            context.confirmation_attempts += 1
            
            if context.confirmation_attempts >= context.max_confirmation_attempts:
                context.current_state = DialogState.ESCALATING
                escalation_message = "I'm having trouble understanding. Let me transfer you to a human representative."
                
                context.conversation_history.append({
                    "role": "assistant",
                    "message": escalation_message,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
                return {
                    "response": escalation_message,
                    "state": context.current_state.value,
                    "next_action": "escalate"
                }
            else:
                # Ask what needs to be changed
                change_message = "What would you like to change about your appointment details?"
                context.current_state = DialogState.COLLECTING_INFO
                
                context.conversation_history.append({
                    "role": "assistant",
                    "message": change_message,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
                return {
                    "response": change_message,
                    "state": context.current_state.value,
                    "next_action": "collect_info"
                }
        else:
            # Unclear response, ask for clarification
            clarification_message = "I didn't quite understand. Please say 'yes' to confirm or 'no' to make changes."
            
            context.conversation_history.append({
                "role": "assistant",
                "message": clarification_message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return {
                "response": clarification_message,
                "state": context.current_state.value,
                "next_action": "confirm_appointment"
            }
    
    async def _handle_booking(self, context: DialogContext, user_input: str) -> Dict[str, Any]:
        """Handle booking state."""
        try:
            # Create appointment using Firebase
            appointment_data = {
                "id": str(uuid.uuid4()),
                "tenant_id": context.tenant_id,
                "call_id": context.call_id,
                "customer_name": context.slots["name"].value,
                "customer_phone": context.slots["phone"].value,
                "customer_email": context.slots["email"].value,
                "service_type": context.slots["service_type"].value,
                "service_address": context.slots["address"].value,
                "appointment_datetime": context.slots["datetime"].value,
                "service_details": context.slots["service_details"].value,
                "status": "scheduled"
            }
            
            appointment = await firebase_service.create_appointment(appointment_data)
            
            if appointment:
                success_message = f"Great! Your {context.service_type} appointment has been booked for {context.slots['datetime'].value}. You'll receive a confirmation email shortly."
                context.current_state = DialogState.ENDING
                
                context.conversation_history.append({
                    "role": "assistant",
                    "message": success_message,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
                return {
                    "response": success_message,
                    "state": context.current_state.value,
                    "next_action": "end_call",
                    "appointment_id": appointment["id"]
                }
            else:
                raise Exception("Failed to create appointment")
                
        except Exception as e:
            error_message = "I'm sorry, there was an issue booking your appointment. Let me transfer you to a human representative."
            context.current_state = DialogState.ESCALATING
            
            context.conversation_history.append({
                "role": "assistant",
                "message": error_message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return {
                "response": error_message,
                "state": context.current_state.value,
                "next_action": "escalate"
            }
    
    async def _handle_escalation(self, context: DialogContext, user_input: str) -> Dict[str, Any]:
        """Handle escalation state."""
        context.escalation_triggered = True
        escalation_message = "You're now being transferred to a human representative. Please hold on."
        
        context.conversation_history.append({
            "role": "assistant",
            "message": escalation_message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {
            "response": escalation_message,
            "state": context.current_state.value,
            "next_action": "escalate"
        }
    
    async def _handle_ending(self, context: DialogContext, user_input: str) -> Dict[str, Any]:
        """Handle ending state."""
        ending_message = "Thank you for calling! Have a great day!"
        
        context.conversation_history.append({
            "role": "assistant",
            "message": ending_message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {
            "response": ending_message,
            "state": context.current_state.value,
            "next_action": "end_call"
        }
    
    async def _extract_information(self, context: DialogContext, user_input: str) -> Dict[str, str]:
        """Extract information from user input using LLM."""
        # This would use an LLM to extract structured information
        # For now, return empty dict (would be implemented with actual LLM)
        return {}
    
    async def _are_all_slots_complete(self, context: DialogContext) -> bool:
        """Check if all required slots are complete."""
        for slot in context.slots.values():
            if slot.required and slot.status != SlotStatus.COMPLETE:
                return False
        return True
    
    async def _get_next_missing_slot(self, context: DialogContext) -> DialogSlot:
        """Get the next missing slot to collect."""
        for slot in context.slots.values():
            if slot.required and slot.status != SlotStatus.COMPLETE:
                return slot
        return list(context.slots.values())[0]  # Fallback
    
    async def _generate_question_for_slot(self, slot: DialogSlot) -> str:
        """Generate a question for a specific slot."""
        questions = {
            "name": "What's your full name?",
            "phone": "What's your phone number?",
            "email": "What's your email address?",
            "service_type": "What type of service do you need?",
            "address": "What's the service address?",
            "datetime": "When would you like to schedule the appointment?",
            "service_details": "Can you provide more details about the service needed?"
        }
        return questions.get(slot.name, f"Please provide your {slot.name}.")
    
    async def _generate_confirmation_message(self, context: DialogContext) -> str:
        """Generate confirmation message with collected information."""
        slots = context.slots
        message = f"Let me confirm your appointment details:\n"
        message += f"Name: {slots['name'].value}\n"
        message += f"Phone: {slots['phone'].value}\n"
        message += f"Email: {slots['email'].value}\n"
        message += f"Service: {slots['service_type'].value}\n"
        message += f"Address: {slots['address'].value}\n"
        message += f"Date & Time: {slots['datetime'].value}\n"
        message += f"Details: {slots['service_details'].value}\n\n"
        message += "Is this information correct?"
        
        return message

# Global dialog manager instance
dialog_manager = DialogManager()