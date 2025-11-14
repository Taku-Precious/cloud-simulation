"""
Network client for CloudSim nodes.
Used to connect to other nodes and send messages.
"""

import socket
import logging
import time
from typing import Optional, Tuple
from .protocol import Message, ProtocolHandler

logger = logging.getLogger(__name__)


class NetworkClient:
    """
    TCP client for connecting to other nodes.
    """
    
    def __init__(self, timeout: float = 10.0):
        """
        Initialize network client.
        
        Args:
            timeout: Socket timeout in seconds
        """
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.remote_address: Optional[Tuple[str, int]] = None
        
    def connect(self, host: str, port: int, retries: int = 3) -> bool:
        """
        Connect to a remote node.
        
        Args:
            host: Remote host address
            port: Remote port number
            retries: Number of connection retries
            
        Returns:
            True if connected successfully
        """
        for attempt in range(retries):
            try:
                # Create socket
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(self.timeout)
                
                # Connect
                logger.debug(f"Connecting to {host}:{port} (attempt {attempt + 1}/{retries})")
                self.socket.connect((host, port))
                
                self.connected = True
                self.remote_address = (host, port)
                logger.info(f"Connected to {host}:{port}")
                return True
                
            except (socket.timeout, ConnectionRefusedError, OSError) as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if self.socket:
                    try:
                        self.socket.close()
                    except:
                        pass
                    self.socket = None
                
                if attempt < retries - 1:
                    time.sleep(1)  # Wait before retry
        
        logger.error(f"Failed to connect to {host}:{port} after {retries} attempts")
        return False
    
    def send_message(self, message: Message, binary_data: Optional[bytes] = None) -> bool:
        """
        Send a message to the connected node.
        
        Args:
            message: Message to send
            binary_data: Optional binary data (for file chunks)
            
        Returns:
            True if sent successfully
        """
        if not self.connected or not self.socket:
            logger.error("Not connected to any node")
            return False
        
        try:
            ProtocolHandler.send_message(self.socket, message, binary_data)
            logger.debug(f"Sent {message.msg_type.value} to {self.remote_address}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.connected = False
            return False
    
    def receive_message(self) -> Optional[Tuple[Message, Optional[bytes]]]:
        """
        Receive a message from the connected node.
        
        Returns:
            (Message, binary_data) tuple, or None if error
        """
        if not self.connected or not self.socket:
            logger.error("Not connected to any node")
            return None
        
        try:
            # Receive complete message
            data = ProtocolHandler.receive_full_message(self.socket)
            
            # Decode message
            message, binary_data = ProtocolHandler.decode_message(data)
            
            logger.debug(f"Received {message.msg_type.value} from {self.remote_address}")
            return (message, binary_data)
            
        except Exception as e:
            logger.error(f"Error receiving message: {e}")
            self.connected = False
            return None
    
    def send_and_receive(self, message: Message, 
                        binary_data: Optional[bytes] = None) -> Optional[Tuple[Message, Optional[bytes]]]:
        """
        Send a message and wait for response.
        
        Args:
            message: Message to send
            binary_data: Optional binary data
            
        Returns:
            (Response message, binary_data) tuple, or None if error
        """
        if not self.send_message(message, binary_data):
            return None
        
        return self.receive_message()
    
    def disconnect(self):
        """Disconnect from the remote node."""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        self.connected = False
        self.remote_address = None
        logger.info("Disconnected")
    
    def is_connected(self) -> bool:
        """Check if connected to a node."""
        return self.connected
    
    def get_remote_address(self) -> Optional[Tuple[str, int]]:
        """Get remote node address."""
        return self.remote_address
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


def send_message_to_node(host: str, port: int, message: Message, 
                        binary_data: Optional[bytes] = None,
                        timeout: float = 10.0) -> Optional[Tuple[Message, Optional[bytes]]]:
    """
    Helper function to send a message to a node and get response.
    
    Args:
        host: Remote host
        port: Remote port
        message: Message to send
        binary_data: Optional binary data
        timeout: Connection timeout
        
    Returns:
        (Response message, binary_data) tuple, or None if error
    """
    with NetworkClient(timeout=timeout) as client:
        if not client.connect(host, port):
            return None
        
        return client.send_and_receive(message, binary_data)

