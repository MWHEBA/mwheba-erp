# ============================================================
# PHASE 5: DATA PROTECTION - DATA ENCRYPTION SERVICE
# ============================================================

"""
Comprehensive data encryption service for protecting sensitive data at rest.
Supports field-level encryption with key rotation and secure key management.
"""

import os
import base64
import hashlib
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
import json

logger = logging.getLogger(__name__)

class DataEncryptionService:
    """
    Comprehensive data encryption service with key management
    """
    
    def __init__(self):
        self.master_key = self._get_master_key()
        self.fernet = Fernet(self.master_key)
        
        # Encryption settings
        self.key_rotation_days = getattr(settings, 'ENCRYPTION_KEY_ROTATION_DAYS', 90)
        self.enable_field_encryption = getattr(settings, 'ENABLE_FIELD_ENCRYPTION', True)
        
        # Sensitive field patterns
        self.sensitive_patterns = [
            'password', 'secret', 'token', 'key', 'ssn', 'national_id',
            'phone', 'email', 'address', 'credit_card', 'bank_account'
        ]
    
    def _get_master_key(self) -> bytes:
        """
        Get or generate master encryption key
        """
        # Try to get key from environment
        env_key = getattr(settings, 'ENCRYPTION_MASTER_KEY', None)
        if env_key:
            try:
                return base64.urlsafe_b64decode(env_key.encode())
            except Exception as e:
                logger.error(f"Invalid master key in environment: {e}")
        
        # Try to get key from file
        key_file = getattr(settings, 'ENCRYPTION_KEY_FILE', 'encryption.key')
        key_path = os.path.join(settings.BASE_DIR, key_file)
        
        if os.path.exists(key_path):
            try:
                with open(key_path, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read key file: {e}")
        
        # Generate new key
        logger.warning("Generating new encryption key - ensure this is backed up securely!")
        key = Fernet.generate_key()
        
        # Save key to file
        try:
            with open(key_path, 'wb') as f:
                f.write(key)
            os.chmod(key_path, 0o600)  # Restrict permissions
        except Exception as e:
            logger.error(f"Failed to save key file: {e}")
        
        return key
    
    def encrypt_field(self, value: Any, field_name: str = None) -> str:
        """
        Encrypt a field value
        """
        if not self.enable_field_encryption:
            return str(value) if value is not None else None
        
        if value is None or value == '':
            return value
        
        try:
            # Convert value to string if needed
            if not isinstance(value, str):
                value = str(value)
            
            # Encrypt the value
            encrypted_bytes = self.fernet.encrypt(value.encode('utf-8'))
            encrypted_str = base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')
            
            # Add metadata
            metadata = {
                'encrypted': True,
                'algorithm': 'fernet',
                'timestamp': datetime.now().isoformat(),
                'field_name': field_name
            }
            
            # Combine metadata and encrypted data
            result = {
                'data': encrypted_str,
                'meta': metadata
            }
            
            return json.dumps(result)
            
        except Exception as e:
            logger.error(f"Encryption failed for field {field_name}: {e}")
            raise ValidationError(f"Failed to encrypt field: {field_name}")
    
    def decrypt_field(self, encrypted_value: str, field_name: str = None) -> Any:
        """
        Decrypt a field value
        """
        if not encrypted_value:
            return encrypted_value
        
        try:
            # Try to parse as JSON (new format)
            try:
                data = json.loads(encrypted_value)
                if isinstance(data, dict) and 'data' in data and 'meta' in data:
                    encrypted_str = data['data']
                    metadata = data['meta']
                    
                    # Verify this is encrypted data
                    if not metadata.get('encrypted', False):
                        return encrypted_value  # Not encrypted
                    
                    encrypted_bytes = base64.urlsafe_b64decode(encrypted_str.encode('utf-8'))
                    decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
                    return decrypted_bytes.decode('utf-8')
            except (json.JSONDecodeError, KeyError):
                # Try legacy format (direct base64)
                try:
                    encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode('utf-8'))
                    decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
                    return decrypted_bytes.decode('utf-8')
                except (InvalidToken, ValueError):
                    # Not encrypted data, return as-is
                    return encrypted_value
            
        except Exception as e:
            logger.error(f"Decryption failed for field {field_name}: {e}")
            # Return original value if decryption fails
            return encrypted_value
    
    def is_field_sensitive(self, field_name: str) -> bool:
        """
        Check if a field should be encrypted based on its name
        """
        field_lower = field_name.lower()
        return any(pattern in field_lower for pattern in self.sensitive_patterns)
    
    def encrypt_model_fields(self, model_instance, field_names: List[str] = None) -> Dict[str, str]:
        """
        Encrypt specified fields of a model instance
        """
        encrypted_fields = {}
        
        if not field_names:
            # Auto-detect sensitive fields
            field_names = [
                field.name for field in model_instance._meta.fields
                if self.is_field_sensitive(field.name)
            ]
        
        for field_name in field_names:
            try:
                value = getattr(model_instance, field_name, None)
                if value is not None:
                    encrypted_value = self.encrypt_field(value, field_name)
                    encrypted_fields[field_name] = encrypted_value
                    setattr(model_instance, field_name, encrypted_value)
            except Exception as e:
                logger.error(f"Failed to encrypt field {field_name}: {e}")
        
        return encrypted_fields
    
    def decrypt_model_fields(self, model_instance, field_names: List[str] = None) -> Dict[str, Any]:
        """
        Decrypt specified fields of a model instance
        """
        decrypted_fields = {}
        
        if not field_names:
            # Auto-detect potentially encrypted fields
            field_names = [
                field.name for field in model_instance._meta.fields
                if self.is_field_sensitive(field.name)
            ]
        
        for field_name in field_names:
            try:
                encrypted_value = getattr(model_instance, field_name, None)
                if encrypted_value is not None:
                    decrypted_value = self.decrypt_field(encrypted_value, field_name)
                    decrypted_fields[field_name] = decrypted_value
                    setattr(model_instance, field_name, decrypted_value)
            except Exception as e:
                logger.error(f"Failed to decrypt field {field_name}: {e}")
        
        return decrypted_fields
    
    def encrypt_file(self, file_path: str, output_path: str = None) -> str:
        """
        Encrypt a file
        """
        if not output_path:
            output_path = file_path + '.encrypted'
        
        try:
            with open(file_path, 'rb') as infile:
                file_data = infile.read()
            
            # Encrypt file data
            encrypted_data = self.fernet.encrypt(file_data)
            
            # Create metadata
            metadata = {
                'original_filename': os.path.basename(file_path),
                'original_size': len(file_data),
                'encrypted_at': datetime.now().isoformat(),
                'algorithm': 'fernet'
            }
            
            # Combine metadata and encrypted data
            with open(output_path, 'wb') as outfile:
                # Write metadata length (4 bytes)
                metadata_json = json.dumps(metadata).encode('utf-8')
                outfile.write(len(metadata_json).to_bytes(4, byteorder='big'))
                
                # Write metadata
                outfile.write(metadata_json)
                
                # Write encrypted data
                outfile.write(encrypted_data)
            
            logger.info(f"File encrypted: {file_path} -> {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"File encryption failed: {e}")
            raise
    
    def decrypt_file(self, encrypted_file_path: str, output_path: str = None) -> str:
        """
        Decrypt a file
        """
        try:
            with open(encrypted_file_path, 'rb') as infile:
                # Read metadata length
                metadata_length = int.from_bytes(infile.read(4), byteorder='big')
                
                # Read metadata
                metadata_json = infile.read(metadata_length)
                metadata = json.loads(metadata_json.decode('utf-8'))
                
                # Read encrypted data
                encrypted_data = infile.read()
            
            # Decrypt data
            decrypted_data = self.fernet.decrypt(encrypted_data)
            
            # Determine output path
            if not output_path:
                output_path = metadata.get('original_filename', 'decrypted_file')
                output_path = os.path.join(
                    os.path.dirname(encrypted_file_path),
                    output_path
                )
            
            # Write decrypted data
            with open(output_path, 'wb') as outfile:
                outfile.write(decrypted_data)
            
            logger.info(f"File decrypted: {encrypted_file_path} -> {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"File decryption failed: {e}")
            raise
    
    def generate_key_pair(self) -> Dict[str, str]:
        """
        Generate RSA key pair for asymmetric encryption
        """
        try:
            # Generate private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            
            # Get public key
            public_key = private_key.public_key()
            
            # Serialize keys
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            return {
                'private_key': private_pem.decode('utf-8'),
                'public_key': public_pem.decode('utf-8')
            }
            
        except Exception as e:
            logger.error(f"Key pair generation failed: {e}")
            raise
    
    def rotate_encryption_key(self) -> Dict[str, Any]:
        """
        Rotate the master encryption key
        """
        rotation_info = {
            'timestamp': datetime.now(),
            'old_key_hash': hashlib.sha256(self.master_key).hexdigest()[:16],
            'status': 'started',
            'errors': []
        }
        
        try:
            logger.info("Starting encryption key rotation")
            
            # Generate new key
            new_key = Fernet.generate_key()
            new_fernet = Fernet(new_key)
            
            # TODO: Re-encrypt all encrypted data with new key
            # This would require identifying all encrypted fields in the database
            # and re-encrypting them with the new key
            
            # Update master key
            old_key = self.master_key
            self.master_key = new_key
            self.fernet = new_fernet
            
            # Save new key
            key_file = getattr(settings, 'ENCRYPTION_KEY_FILE', 'encryption.key')
            key_path = os.path.join(settings.BASE_DIR, key_file)
            
            # Backup old key
            backup_path = key_path + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if os.path.exists(key_path):
                os.rename(key_path, backup_path)
            
            # Save new key
            with open(key_path, 'wb') as f:
                f.write(new_key)
            os.chmod(key_path, 0o600)
            
            rotation_info['new_key_hash'] = hashlib.sha256(new_key).hexdigest()[:16]
            rotation_info['status'] = 'completed'
            
            logger.info("Encryption key rotation completed successfully")
            
        except Exception as e:
            rotation_info['status'] = 'failed'
            rotation_info['errors'].append(str(e))
            logger.error(f"Key rotation failed: {e}")
            raise
        
        return rotation_info
    
    def anonymize_data(self, data: Dict[str, Any], anonymization_rules: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Anonymize sensitive data for testing/development
        """
        if not anonymization_rules:
            anonymization_rules = {
                'email': 'user{}@example.com',
                'phone': '+1-555-0{:03d}',
                'national_id': '{:014d}',
                'name': 'User {}',
                'address': '{} Anonymous Street',
                'ssn': 'XXX-XX-{:04d}'
            }
        
        anonymized_data = data.copy()
        counter = 1
        
        for field_name, value in data.items():
            if value is None:
                continue
            
            field_lower = field_name.lower()
            
            # Find matching anonymization rule
            for pattern, template in anonymization_rules.items():
                if pattern in field_lower:
                    try:
                        if '{}' in template:
                            anonymized_data[field_name] = template.format(counter)
                        elif '{:' in template:
                            anonymized_data[field_name] = template.format(counter)
                        else:
                            anonymized_data[field_name] = template
                        counter += 1
                        break
                    except Exception as e:
                        logger.error(f"Anonymization failed for {field_name}: {e}")
        
        return anonymized_data
    
    def create_data_mask(self, value: str, mask_char: str = '*', 
                        visible_start: int = 2, visible_end: int = 2) -> str:
        """
        Create a masked version of sensitive data
        """
        if not value or len(value) <= (visible_start + visible_end):
            return mask_char * len(value) if value else value
        
        start_part = value[:visible_start]
        end_part = value[-visible_end:] if visible_end > 0 else ''
        middle_length = len(value) - visible_start - visible_end
        middle_part = mask_char * middle_length
        
        return start_part + middle_part + end_part
    
    def validate_encryption_integrity(self) -> Dict[str, Any]:
        """
        Validate encryption system integrity
        """
        validation_result = {
            'timestamp': datetime.now(),
            'status': 'success',
            'tests_passed': 0,
            'tests_failed': 0,
            'errors': []
        }
        
        try:
            # Test 1: Basic encryption/decryption
            test_data = "Test encryption data 123!@#"
            encrypted = self.encrypt_field(test_data, 'test_field')
            decrypted = self.decrypt_field(encrypted, 'test_field')
            
            if decrypted == test_data:
                validation_result['tests_passed'] += 1
            else:
                validation_result['tests_failed'] += 1
                validation_result['errors'].append("Basic encryption/decryption test failed")
            
            # Test 2: Key availability
            if self.master_key and len(self.master_key) == 44:  # Fernet key length
                validation_result['tests_passed'] += 1
            else:
                validation_result['tests_failed'] += 1
                validation_result['errors'].append("Master key validation failed")
            
            # Test 3: File encryption
            test_file_content = b"Test file content for encryption"
            test_file_path = "/tmp/test_encryption_file.txt"
            
            try:
                with open(test_file_path, 'wb') as f:
                    f.write(test_file_content)
                
                encrypted_file = self.encrypt_file(test_file_path)
                decrypted_file = self.decrypt_file(encrypted_file)
                
                with open(decrypted_file, 'rb') as f:
                    decrypted_content = f.read()
                
                if decrypted_content == test_file_content:
                    validation_result['tests_passed'] += 1
                else:
                    validation_result['tests_failed'] += 1
                    validation_result['errors'].append("File encryption test failed")
                
                # Cleanup
                for file_path in [test_file_path, encrypted_file, decrypted_file]:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                        
            except Exception as e:
                validation_result['tests_failed'] += 1
                validation_result['errors'].append(f"File encryption test error: {e}")
            
            # Set overall status
            if validation_result['tests_failed'] > 0:
                validation_result['status'] = 'failed'
            
        except Exception as e:
            validation_result['status'] = 'error'
            validation_result['errors'].append(str(e))
        
        return validation_result


class EncryptedField:
    """
    Custom field descriptor for automatic encryption/decryption
    """
    
    def __init__(self, field_name: str):
        self.field_name = field_name
        self.encryption_service = DataEncryptionService()
    
    def __get__(self, instance, owner):
        if instance is None:
            return self
        
        encrypted_value = getattr(instance, f'_{self.field_name}', None)
        if encrypted_value is None:
            return None
        
        return self.encryption_service.decrypt_field(encrypted_value, self.field_name)
    
    def __set__(self, instance, value):
        if value is None:
            setattr(instance, f'_{self.field_name}', None)
        else:
            encrypted_value = self.encryption_service.encrypt_field(value, self.field_name)
            setattr(instance, f'_{self.field_name}', encrypted_value)


def encrypt_sensitive_fields(sender, instance, **kwargs):
    """
    Signal handler to automatically encrypt sensitive fields before saving
    """
    encryption_service = DataEncryptionService()
    
    # Get fields to encrypt from model meta or auto-detect
    fields_to_encrypt = getattr(instance._meta, 'encrypted_fields', None)
    
    if not fields_to_encrypt:
        # Auto-detect sensitive fields
        fields_to_encrypt = [
            field.name for field in instance._meta.fields
            if encryption_service.is_field_sensitive(field.name)
        ]
    
    if fields_to_encrypt:
        encryption_service.encrypt_model_fields(instance, fields_to_encrypt)


def decrypt_sensitive_fields(sender, instance, **kwargs):
    """
    Signal handler to automatically decrypt sensitive fields after loading
    """
    encryption_service = DataEncryptionService()
    
    # Get fields to decrypt from model meta or auto-detect
    fields_to_decrypt = getattr(instance._meta, 'encrypted_fields', None)
    
    if not fields_to_decrypt:
        # Auto-detect potentially encrypted fields
        fields_to_decrypt = [
            field.name for field in instance._meta.fields
            if encryption_service.is_field_sensitive(field.name)
        ]
    
    if fields_to_decrypt:
        encryption_service.decrypt_model_fields(instance, fields_to_decrypt)