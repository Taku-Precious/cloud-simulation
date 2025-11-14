"""
Network server for CloudSim nodes.
Each node runs a server to accept connections from other nodes.
"""

import socket
import threading
import logging
from typing import Callable, Dict, Any, Optional
from .protocol import Message, MessageType, ProtocolHandler, create_error_message

logger = logging.getLogger(__name__)


class NetworkServer:
    """
    TCP server for receiving network connections.
    Each node runs one server instance.
    """
    
    def __init__(self, host: str, port: int, message_handler: Callable[[Message, socket.socket], None]):
        """
        Initialize network server.
        
        Args:
            host: Host address to bind to (e.g., '0.0.0.0', 'localhost')
            port: Port number to listen on
            message_handler: Callback function to handle received messages
        """
        self.host = host
        self.port = port
        self.message_handler = message_handler
        
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.server_thread: Optional[threading.Thread] = None
        
        # Track active connections
        self.active_connections: Dict[str, socket.socket] = {}
        self.connection_lock = threading.Lock()
        
        logger.info(f"NetworkServer initialized on {host}:{port}")
    
    def start(self):
        """Start the server in a background thread."""
        if self.running:
            logger.warning("Server already running")
            return
        
        self.running = True
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()
        logger.info(f"Server started on {self.host}:{self.port}")
    
    def stop(self):
        """Stop the server and close all connections."""
        if not self.running:
            return
        
        logger.info("Stopping server...")
        self.running = False
        
        # Close all active connections
        with self.connection_lock:
            for conn_id, sock in list(self.active_connections.items()):
                try:
                    sock.close()
                except:
                    pass
            self.active_connections.clear()
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        # Wait for server thread
        if self.server_thread:
            self.server_thread.join(timeout=5)
        
        logger.info("Server stopped")
    
    def _run_server(self):
        """Main server loop (runs in background thread)."""
        try:
            # Create server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            
            logger.info(f"Server listening on {self.host}:{self.port}")
            
            # Accept connections
            while self.running:
                try:
                    # Set timeout so we can check self.running periodically
                    self.server_socket.settimeout(1.0)
                    
                    try:
                        client_socket, client_address = self.server_socket.accept()
                    except socket.timeout:
                        continue
                    
                    logger.info(f"New connection from {client_address}")
                    
                    # Handle client in separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}")
        
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()
    
    def _handle_client(self, client_socket: socket.socket, client_address: tuple):
        """
        Handle a client connection.
        
        Args:
            client_socket: Client socket
            client_address: Client address (host, port)
        """
        conn_id = f"{client_address[0]}:{client_address[1]}"
        
        try:
            # Register connection
            with self.connection_lock:
                self.active_connections[conn_id] = client_socket
            
            # Receive and process messages
            while self.running:
                try:
                    # Receive complete message
                    data = ProtocolHandler.receive_full_message(client_socket)
                    
                    # Decode message
                    message, binary_data = ProtocolHandler.decode_message(data)
                    
                    # Add binary data to message if present
                    if binary_data:
                        message.data['_binary_data'] = binary_data
                    
                    logger.debug(f"Received {message.msg_type.value} from {conn_id}")
                    
                    # Handle message
                    try:
                        self.message_handler(message, client_socket)
                    except Exception as e:
                        logger.error(f"Error handling message: {e}")
                        # Send error response
                        error_msg = create_error_message(str(e))
                        try:
                            ProtocolHandler.send_message(client_socket, error_msg)
                        except:
                            pass
                
                except ConnectionError:
                    logger.info(f"Connection closed by {conn_id}")
                    break
                except Exception as e:
                    logger.error(f"Error receiving message from {conn_id}: {e}")
                    break
        
        finally:
            # Cleanup
            with self.connection_lock:
                self.active_connections.pop(conn_id, None)
            
            try:
                client_socket.close()
            except:
                pass
            
            logger.info(f"Connection {conn_id} closed")
    
    def get_address(self) -> tuple[str, int]:
        """Get server address."""
        return (self.host, self.port)
    
    def is_running(self) -> bool:
        """Check if server is running."""
        return self.running
    
    def get_active_connections_count(self) -> int:
        """Get number of active connections."""
        with self.connection_lock:
            return len(self.active_connections)

