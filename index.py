import requests
import time
import json
import os
from datetime import datetime
import logging
from typing import Optional, Dict

class WebRadioMonitor:
    def __init__(self, stream_url: str, lb_token: str):
        self.stream_url = stream_url
        self.lb_token = lb_token
        self.last_track = None
        self.headers = {
            'Authorization': f'Token {lb_token}',
            'Content-Type': 'application/json'
        }
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def fetch_metadata(self) -> Optional[Dict]:
        """
        Fetch metadata using ICY (Shoutcast) protocol
        """
        try:
            headers = {
                'Icy-MetaData': '1',
                'User-Agent': 'Mozilla/5.0' 
            }
            
            response = requests.get(
                self.stream_url, 
                headers=headers, 
                stream=True,
                timeout=15
            )

            if 'icy-metaint' in response.headers:
                metaint = int(response.headers['icy-metaint'])
                for _ in range(10):
                    response.raw.read(metaint)
                    length = response.raw.read(1)
                    if length:
                        length = ord(length) * 16
                        if length > 0:
                            metadata = response.raw.read(length).decode('utf-8', errors='ignore')
                            if metadata:
                                if 'StreamTitle=' in metadata:
                                    title = metadata.split('StreamTitle=')[1].split(';')[0].strip("'")
                                    if ' - ' in title:
                                        artist, track = title.split(' - ', 1)
                                        return {
                                            'artist': artist.strip(),
                                            'track': track.strip()
                                        }
                                    else:
                                        return {
                                            'artist': 'Unknown Artist',
                                            'track': title.strip()
                                        }
            
            if 'icy-name' in response.headers:
                return {
                    'artist': response.headers.get('icy-name', 'Unknown Station'),
                    'track': 'Current Track'
                }

            self.logger.error("No ICY metadata found in stream")
            return None

        except Exception as e:
            self.logger.error(f"Error fetching ICY metadata: {e}")
            return None
        
    def submit_to_listenbrainz(self, metadata: Dict) -> bool:
        """Submit the track to ListenBrainz"""
        if not metadata:
            self.logger.error("No metadata provided for submission")
            return False

        try:
            if not isinstance(metadata.get('artist'), str) or not isinstance(metadata.get('track'), str):
                self.logger.error("Invalid metadata format: artist and track must be strings")
                return False

            payload = {
                "listen_type": "single",
                "payload": [{
                    "listened_at": int(time.time()),
                    "track_metadata": {
                        "additional_info": {
                            "submission_client": "webradio-monitor",
                            "submission_client_version": "1.0"
                        },
                        "artist_name": metadata['artist'],
                        "track_name": metadata['track']
                    }
                }]
            }

            self.logger.debug(f"Submitting payload to ListenBrainz: {json.dumps(payload, indent=2)}")
            
            response = requests.post(
                "https://api.listenbrainz.org/1/submit-listens",
                headers=self.headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code != 200:
                self.logger.error(f"ListenBrainz API error: Status {response.status_code}")
                self.logger.error(f"Response: {response.text}")
                return False
                
            return True
            
        except requests.exceptions.Timeout:
            self.logger.error("Timeout while submitting to ListenBrainz")
            return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error while submitting to ListenBrainz: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error submitting to ListenBrainz: {e}")
            return False

    def run(self, check_interval: int = 30):
        """Main loop to monitor and submit tracks"""
        self.logger.info("Starting WebRadio monitor...")
        
        while True:
            metadata = self.fetch_metadata()
            
            if metadata and metadata != self.last_track:
                self.logger.info(f"New track: {metadata['artist']} - {metadata['track']}")
                if self.submit_to_listenbrainz(metadata):
                    self.logger.info("Successfully submitted to ListenBrainz")
                    self.last_track = metadata
                else:
                    self.logger.error("Failed to submit to ListenBrainz")
            
            time.sleep(check_interval)

def main():
    stream_url = "https://stream.srg-ssr.ch/m/rsj/aacp_96"
    lb_token = "your-listenbrainz-token-here"  

    monitor = WebRadioMonitor(stream_url, lb_token)
    monitor.run()

if __name__ == '__main__':
    main()