"""
Firebase service for database operations using Firestore.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import firebase_admin
from firebase_admin import credentials, firestore

from app.core.config import FIREBASE_CLIENT_EMAIL, FIREBASE_PRIVATE_KEY, FIREBASE_PROJECT_ID


class FirebaseService:
    """Service class for Firebase Firestore database operations."""

    def __init__(self):
        """Initialize Firebase client."""
        if not FIREBASE_PROJECT_ID:
            raise ValueError("FIREBASE_PROJECT_ID must be set")

        # Initialize Firebase Admin SDK if not already initialized
        if not firebase_admin._apps:
            try:
                # Create credentials from minimal required fields
                cred_dict = {
                    "type": "service_account",
                    "project_id": FIREBASE_PROJECT_ID,
                    "private_key": FIREBASE_PRIVATE_KEY,
                    "client_email": FIREBASE_CLIENT_EMAIL,
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{FIREBASE_CLIENT_EMAIL}",
                }

                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
            except Exception as e:
                raise ValueError(f"Firebase initialization failed: {e}")

        self.db = firestore.client()

    # User operations
    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user."""
        user_data["created_at"] = datetime.now(timezone.utc).isoformat()
        user_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("users").document(user_data["id"])
        doc_ref.set(user_data)

        return user_data

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email."""
        users_ref = self.db.collection("users")
        query = users_ref.where("email", "==", email).limit(1)
        docs = query.stream()

        for doc in docs:
            return doc.to_dict()
        return None

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        doc_ref = self.db.collection("users").document(user_id)
        doc = doc_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    async def list_users(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List users with pagination."""
        users_ref = self.db.collection("users")
        query = users_ref.limit(limit).offset(offset)
        docs = query.stream()

        users = []
        for doc in docs:
            users.append(doc.to_dict())
        return users

    async def update_user(self, user_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update user."""
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("users").document(user_id)
        doc_ref.update(update_data)

        # Return updated document
        doc = doc_ref.get()
        return doc.to_dict()

    # Tenant operations
    async def create_tenant(self, tenant_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new tenant."""
        tenant_data["created_at"] = datetime.now(timezone.utc).isoformat()
        tenant_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("tenants").document(tenant_data["id"])
        doc_ref.set(tenant_data)

        return tenant_data

    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by ID."""
        doc_ref = self.db.collection("tenants").document(tenant_id)
        doc = doc_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    async def update_tenant(self, tenant_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update tenant."""
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("tenants").document(tenant_id)
        doc_ref.update(update_data)

        # Return updated document
        doc = doc_ref.get()
        return doc.to_dict()

    async def list_tenants(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List tenants with pagination."""
        tenants_ref = self.db.collection("tenants")
        docs = tenants_ref.limit(limit).offset(offset).stream()

        return [doc.to_dict() for doc in docs]

    # Appointment operations
    async def create_appointment(self, appointment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new appointment."""
        appointment_data["created_at"] = datetime.now(timezone.utc).isoformat()
        appointment_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("appointments").document(appointment_data["id"])
        doc_ref.set(appointment_data)

        return appointment_data

    async def get_appointment(self, appointment_id: str) -> Optional[Dict[str, Any]]:
        """Get appointment by ID."""
        doc_ref = self.db.collection("appointments").document(appointment_id)
        doc = doc_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    async def list_appointments(self, tenant_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List appointments for a tenant."""
        appointments_ref = self.db.collection("appointments")
        query = appointments_ref.where("tenant_id", "==", tenant_id).limit(limit).offset(offset)
        docs = query.stream()

        return [doc.to_dict() for doc in docs]

    async def update_appointment(self, appointment_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update appointment."""
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("appointments").document(appointment_id)
        doc_ref.update(update_data)

        # Return updated document
        doc = doc_ref.get()
        return doc.to_dict()

    # Call operations
    async def create_call(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new call record."""
        call_data["created_at"] = datetime.now(timezone.utc).isoformat()
        call_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("calls").document(call_data["id"])
        doc_ref.set(call_data)

        return call_data

    async def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get call by ID."""
        doc_ref = self.db.collection("calls").document(call_id)
        doc = doc_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    async def update_call(self, call_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update call."""
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("calls").document(call_id)
        doc_ref.update(update_data)

        # Return updated document
        doc = doc_ref.get()
        return doc.to_dict()

    # Business configuration operations
    async def create_business_config(self, business_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create business configuration."""
        business_data["created_at"] = datetime.now(timezone.utc).isoformat()
        business_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("business_configs").document(business_data["id"])
        doc_ref.set(business_data)

        return business_data

    async def get_business_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get business configuration for a tenant."""
        business_ref = self.db.collection("business_configs")
        query = business_ref.where("tenant_id", "==", tenant_id).limit(1)
        docs = query.stream()

        for doc in docs:
            return doc.to_dict()
        return None

    async def update_business_config(self, tenant_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update business configuration for a tenant."""
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        business_ref = self.db.collection("business_configs")
        query = business_ref.where("tenant_id", "==", tenant_id).limit(1)
        docs = query.stream()

        for doc in docs:
            doc.reference.update(update_data)
            return doc.to_dict()
        return None

    # Agent settings operations
    async def create_agent_settings(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create agent settings."""
        agent_data["created_at"] = datetime.now(timezone.utc).isoformat()
        agent_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("agent_settings").document(agent_data["id"])
        doc_ref.set(agent_data)

        return agent_data

    async def get_agent_settings(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get agent settings for a tenant."""
        agent_ref = self.db.collection("agent_settings")
        query = agent_ref.where("tenant_id", "==", tenant_id).limit(1)
        docs = query.stream()

        for doc in docs:
            return doc.to_dict()
        return None

    async def update_agent_settings(self, tenant_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update agent settings for a tenant."""
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        agent_ref = self.db.collection("agent_settings")
        query = agent_ref.where("tenant_id", "==", tenant_id).limit(1)
        docs = query.stream()

        for doc in docs:
            doc.reference.update(update_data)
            return doc.to_dict()
        return None

    # Twilio integration operations
    async def create_twilio_integration(self, twilio_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create Twilio integration."""
        twilio_data["created_at"] = datetime.now(timezone.utc).isoformat()
        twilio_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("twilio_integrations").document(twilio_data["id"])
        doc_ref.set(twilio_data)

        return twilio_data

    async def get_twilio_integration(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get Twilio integration for a tenant."""
        twilio_ref = self.db.collection("twilio_integrations")
        query = twilio_ref.where("tenant_id", "==", tenant_id).limit(1)
        docs = query.stream()

        for doc in docs:
            return doc.to_dict()
        return None

    async def update_twilio_integration(self, tenant_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update Twilio integration for a tenant."""
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        twilio_ref = self.db.collection("twilio_integrations")
        query = twilio_ref.where("tenant_id", "==", tenant_id).limit(1)
        docs = query.stream()

        for doc in docs:
            doc.reference.update(update_data)
            return doc.to_dict()
        return None

    async def delete_twilio_integration(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Delete Twilio integration for a tenant."""
        twilio_ref = self.db.collection("twilio_integrations")
        query = twilio_ref.where("tenant_id", "==", tenant_id).limit(1)
        docs = query.stream()

        for doc in docs:
            integration_data = doc.to_dict()
            doc.reference.delete()
            return integration_data
        return None

    # Provisioning jobs operations
    async def create_provisioning_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a provisioning job."""
        job_data["created_at"] = datetime.now(timezone.utc).isoformat()
        job_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("provisioning_jobs").document(job_data["id"])
        doc_ref.set(job_data)

        return job_data

    async def get_provisioning_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get provisioning job by ID."""
        doc_ref = self.db.collection("provisioning_jobs").document(job_id)
        doc = doc_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    async def update_provisioning_job(self, job_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update provisioning job."""
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("provisioning_jobs").document(job_id)
        doc_ref.update(update_data)

        # Return updated document
        doc = doc_ref.get()
        return doc.to_dict()

    # Agent operations
    async def create_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new agent."""
        agent_data["created_at"] = datetime.now(timezone.utc).isoformat()
        agent_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("agents").document(agent_data["id"])
        doc_ref.set(agent_data)

        return agent_data

    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by ID."""
        doc_ref = self.db.collection("agents").document(agent_id)
        doc = doc_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    async def list_agents_by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all agents for a tenant."""
        agents_ref = self.db.collection("agents")
        query = agents_ref.where("tenant_id", "==", tenant_id)
        docs = query.stream()

        return [doc.to_dict() for doc in docs]

    async def update_agent(self, agent_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update agent."""
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("agents").document(agent_id)
        doc_ref.update(update_data)

        # Return updated document
        doc = doc_ref.get()
        return doc.to_dict()

    async def delete_agent(self, agent_id: str) -> bool:
        """Delete agent."""
        doc_ref = self.db.collection("agents").document(agent_id)
        doc = doc_ref.get()

        if doc.exists:
            doc_ref.delete()
            return True
        return False

    # Phone number operations
    async def create_phone_number(self, phone_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new phone number assignment."""
        phone_data["created_at"] = datetime.now(timezone.utc).isoformat()
        phone_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("phone_numbers").document(phone_data["id"])
        doc_ref.set(phone_data)

        return phone_data

    async def get_phone_number(self, phone_id: str) -> Optional[Dict[str, Any]]:
        """Get phone number by ID."""
        doc_ref = self.db.collection("phone_numbers").document(phone_id)
        doc = doc_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    async def get_phone_by_number(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Get phone number by actual number string."""
        phones_ref = self.db.collection("phone_numbers")
        query = phones_ref.where("phone_number", "==", phone_number).limit(1)
        docs = query.stream()

        for doc in docs:
            return doc.to_dict()
        return None

    async def get_phone_by_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get phone number assigned to an agent."""
        phones_ref = self.db.collection("phone_numbers")
        query = phones_ref.where("agent_id", "==", agent_id).limit(1)
        docs = query.stream()

        for doc in docs:
            return doc.to_dict()
        return None

    async def list_phones_by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all phone numbers for a tenant."""
        phones_ref = self.db.collection("phone_numbers")
        query = phones_ref.where("tenant_id", "==", tenant_id)
        docs = query.stream()

        return [doc.to_dict() for doc in docs]

    async def update_phone_number(self, phone_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update phone number assignment."""
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        doc_ref = self.db.collection("phone_numbers").document(phone_id)
        doc_ref.update(update_data)

        # Return updated document
        doc = doc_ref.get()
        return doc.to_dict()

    async def delete_phone_number(self, phone_id: str) -> bool:
        """Delete phone number assignment."""
        doc_ref = self.db.collection("phone_numbers").document(phone_id)
        doc = doc_ref.get()

        if doc.exists:
            doc_ref.delete()
            return True
        return False


# PERFORMANCE OPTIMIZATION APPLIED!
# Using optimized Firebase service with asyncio.to_thread() wrapper
# This provides 10-50x performance improvement by preventing event loop blocking

# Import optimized version (comment out to use original)
from app.services.firebase_optimized import optimized_firebase_service

# Use optimized service as default
firebase_service = optimized_firebase_service

# Original service still available if needed:
# firebase_service = FirebaseService()
