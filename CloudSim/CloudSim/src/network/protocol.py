"""
Network protocol definitions for CloudSim distributed system.
Defines message types and protocol handling.
"""

import json
import struct
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


class MessageType(Enum):
    """Types of messages exchanged between nodes."""
    
    # Node registration and discovery
    REGISTER_NODE = "REGISTER_NODE"
    NODE_REGISTERED = "NODE_REGISTERED"
    DISCOVER_NODES = "DISCOVER_NODES"
    NODES_LIST = "NODES_LIST"
    
    # Heartbeat
    HEARTBEAT = "HEARTBEAT"
    HEARTBEAT_ACK = "HEARTBEAT_ACK"
    
    # File operations
    UPLOAD_FILE = "UPLOAD_FILE"
    UPLOAD_ACK = "UPLOAD_ACK"
    DOWNLOAD_FILE = "DOWNLOAD_FILE"
    FILE_DATA = "FILE_DATA"
    
    # Chunk operations
    STORE_CHUNK = "STORE_CHUNK"
    CHUNK_STORED = "CHUNK_STORED"
    GET_CHUNK = "GET_CHUNK"
    CHUNK_DATA = "CHUNK_DATA"
    REPLICATE_CHUNK = "REPLICATE_CHUNK"
    
    # Status and monitoring
    GET_STATUS = "GET_STATUS"
    STATUS_RESPONSE = "STATUS_RESPONSE"
    NODE_FAILURE = "NODE_FAILURE"
    
    # Errors
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


@dataclass
class Message:
    """Network message structure."""
    
    msg_type: MessageType
    data: Dict[str, Any]
    sender_id: Optional[str] = None
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            'msg_type': self.msg_type.value,
            'data': self.data,
            'sender_id': self.sender_id,
            'request_id': self.request_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create message from dictionary."""
        return cls(
            msg_type=MessageType(data['msg_type']),
            data=data['data'],
            sender_id=data.get('sender_id'),
            request_id=data.get('request_id')
        )
    
    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """Create message from JSON string."""
        return cls.from_dict(json.loads(json_str))


class ProtocolHandler:
    """Handles network protocol encoding/decoding."""
    
    # Protocol format:
    #   [4 bytes total length][4 bytes JSON length][JSON][optional binary data]
    HEADER_SIZE = 4
    JSON_LENGTH_SIZE = 4
    MAX_MESSAGE_SIZE = 100 * 1024 * 1024  # 100 MB
    
    @staticmethod
    def encode_message(message: Message, binary_data: Optional[bytes] = None) -> bytes:
        """
        Encode message to bytes for network transmission.
        
        Format:
        - 4 bytes: Total message length (header + JSON + binary)
        - N bytes: JSON message
        - M bytes: Optional binary data (for file chunks)
        """
        # Encode JSON message
        json_bytes = message.to_json().encode('utf-8')
        json_length = len(json_bytes)
        binary_length = len(binary_data) if binary_data else 0

        # Calculate total payload length (json length prefix + json + binary)
        total_length = ProtocolHandler.JSON_LENGTH_SIZE + json_length + binary_length

        # Create headers (big-endian)
        header = struct.pack('>I', total_length)
        json_header = struct.pack('>I', json_length)

        if binary_data:
            return header + json_header + json_bytes + binary_data
        return header + json_header + json_bytes
    
    @staticmethod
    def decode_message(data: bytes) -> tuple[Message, Optional[bytes]]:
        """
        Decode message from bytes.
        
        Returns:
            (Message, binary_data) tuple
        """
        if len(data) < ProtocolHandler.HEADER_SIZE:
            raise ValueError("Data too short for protocol header")
        
        # Read header
        header = data[:ProtocolHandler.HEADER_SIZE]
        total_length = struct.unpack('>I', header)[0]
        
        if total_length > ProtocolHandler.MAX_MESSAGE_SIZE:
            raise ValueError(f"Message too large: {total_length} bytes")
        
        # Extract payload
        payload = data[ProtocolHandler.HEADER_SIZE:ProtocolHandler.HEADER_SIZE + total_length]
        
        if len(payload) < ProtocolHandler.JSON_LENGTH_SIZE:
            raise ValueError("Payload too short for JSON length header")
        
        json_length = struct.unpack('>I', payload[:ProtocolHandler.JSON_LENGTH_SIZE])[0]
        
        if json_length < 0 or json_length > total_length - ProtocolHandler.JSON_LENGTH_SIZE:
            raise ValueError("Invalid JSON length in payload")
        
        json_start = ProtocolHandler.JSON_LENGTH_SIZE
        json_end = json_start + json_length
        json_bytes = payload[json_start:json_end]
        message = Message.from_json(json_bytes.decode('utf-8'))
        
        binary_data = None
        if json_end < len(payload):
            binary_data = payload[json_end:]
        
        return message, binary_data
    
    @staticmethod
    def receive_full_message(sock) -> bytes:
        """
        Receive a complete message from socket.
        
        Args:
            sock: Socket to receive from
            
        Returns:
            Complete message bytes
        """
        # First, receive the header
        header = b''
        while len(header) < ProtocolHandler.HEADER_SIZE:
            chunk = sock.recv(ProtocolHandler.HEADER_SIZE - len(header))
            if not chunk:
                raise ConnectionError("Connection closed while receiving header")
            header += chunk
        
        # Parse header to get message length
        total_length = struct.unpack('>I', header)[0]
        
        if total_length > ProtocolHandler.MAX_MESSAGE_SIZE:
            raise ValueError(f"Message too large: {total_length} bytes")
        
        # Receive the full message
        message_data = b''
        while len(message_data) < total_length:
            chunk = sock.recv(min(8192, total_length - len(message_data)))
            if not chunk:
                raise ConnectionError("Connection closed while receiving message")
            message_data += chunk
        
        return header + message_data
    
    @staticmethod
    def send_message(sock, message: Message, binary_data: Optional[bytes] = None):
        """
        Send a complete message through socket.
        
        Args:
            sock: Socket to send through
            message: Message to send
            binary_data: Optional binary data (for file chunks)
        """
        encoded = ProtocolHandler.encode_message(message, binary_data)
        
        # Send all data
        total_sent = 0
        while total_sent < len(encoded):
            sent = sock.send(encoded[total_sent:])
            if sent == 0:
                raise ConnectionError("Socket connection broken")
            total_sent += sent


def create_message(msg_type: MessageType, data: Dict[str, Any], 
                   sender_id: Optional[str] = None,
                   request_id: Optional[str] = None) -> Message:
    """Helper function to create messages."""
    return Message(
        msg_type=msg_type,
        data=data,
        sender_id=sender_id,
        request_id=request_id
    )


def create_error_message(error: str, sender_id: Optional[str] = None) -> Message:
    """Helper function to create error messages."""
    return create_message(
        MessageType.ERROR,
        {'error': error},
        sender_id=sender_id
    )


def create_success_message(data: Dict[str, Any] = None, 
                          sender_id: Optional[str] = None) -> Message:
    """Helper function to create success messages."""
    return create_message(
        MessageType.SUCCESS,
        data or {},
        sender_id=sender_id
    )

