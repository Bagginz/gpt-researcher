from google.cloud import pubsub_v1
from google.oauth2 import service_account
import jwt
import os
import json

# Set the Google Cloud project and Pub/Sub topic
class PublishManager:
    """Manage Google Publish Message"""
    def __init__(self):
        """Initialize the Google PubSub class."""

    def publish_message(self, message_data):
        """Publish a message to the topic."""
        secret_key = os.environ.get("JWT_SECRET_KEY", None)
        pub_topic_name = os.environ.get("PUB_TOPIC", None)
        project_id = os.environ.get("PROJECT_ID", None)
        auth_file = os.environ.get("AUTH_JSON", None)

        if not secret_key or not pub_topic_name or not project_id or not auth_file:
            raise Exception("JWT_SECRET_KEY not set.")

        credentials = service_account.Credentials.from_service_account_file(auth_file)
        self.publisher = pubsub_v1.PublisherClient(credentials=credentials)

        encoded_payload = jwt.encode(message_data, secret_key, algorithm='HS256')
        payload = { "message": encoded_payload, "message_type": message_data.get("message_type") }
        # Define the topic path
        topic_path = self.publisher.topic_path(project_id, pub_topic_name)

        json_string = json.dumps(payload)
        # Publish a message to the topic
        future = self.publisher.publish(topic_path, data=json_string.encode('UTF-8'))
        # Wait for the message to be published
        message_id = future.result()
        print(f"Published message to {pub_topic_name} : {message_id}")
