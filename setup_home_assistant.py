#!/usr/bin/env python3
"""
Quick setup script for Home Assistant integration.
This script generates the configuration snippets needed for Home Assistant.
"""

import os
import yaml
from pathlib import Path

def generate_ha_config():
    """Generate Home Assistant configuration snippets."""
    
    # Get current directory for absolute paths
    current_dir = Path(__file__).parent.absolute()
    
    config = {
        'rest_command': {
            'download_kukaj_video': {
                'url': 'http://localhost:8080/api/download',
                'method': 'POST',
                'headers': {
                    'Content-Type': 'application/json'
                },
                'payload': '''
{
  "url": "{{ url }}",
  "format": "{{ format | default('m3u8') }}",
  "filename": "{{ filename | default('') }}"
}'''.strip()
            }
        },
        'sensor': [
            {
                'platform': 'rest',
                'name': 'Kukaj Downloads',
                'resource': 'http://localhost:8080/api/downloads',
                'scan_interval': 30,
                'value_template': '{{ value_json | length }}',
                'json_attributes': ['downloads']
            }
        ],
        'shell_command': {
            'download_kukaj_m3u8': f"cd '{current_dir}' && python3 kukaj_downloader.py '{{{{ url }}}}' -o '{{{{ filename }}}}'",
            'download_kukaj_mp4': f"cd '{current_dir}' && python3 kukaj_downloader.py '{{{{ url }}}}' --mp4 -o '{{{{ filename }}}}'",
            'cleanup_downloads': f"find '{current_dir}/downloads' -type f -mtime +7 -delete"
        },
        'script': {
            'download_video': {
                'alias': 'Download Kukaj Video',
                'fields': {
                    'url': {
                        'description': 'Video URL',
                        'example': 'https://serial.kukaj.fi/hra-na-olihen/S03E04'
                    },
                    'format': {
                        'description': 'Format (m3u8 or mp4)',
                        'example': 'mp4'
                    },
                    'filename': {
                        'description': 'Custom filename',
                        'example': 'my-video'
                    }
                },
                'sequence': [
                    {
                        'choose': [
                            {
                                'conditions': [
                                    {
                                        'condition': 'template',
                                        'value_template': "{{ format == 'mp4' }}"
                                    }
                                ],
                                'sequence': [
                                    {
                                        'service': 'shell_command.download_kukaj_mp4',
                                        'data': {
                                            'url': '{{ url }}',
                                            'filename': '{{ filename }}'
                                        }
                                    }
                                ]
                            }
                        ],
                        'default': [
                            {
                                'service': 'shell_command.download_kukaj_m3u8',
                                'data': {
                                    'url': '{{ url }}',
                                    'filename': '{{ filename }}'
                                }
                            }
                        ]
                    }
                ]
            }
        },
        'automation': [
            {
                'alias': 'Download Video from Webhook',
                'trigger': {
                    'platform': 'webhook',
                    'webhook_id': 'kukaj_download'
                },
                'action': {
                    'service': 'rest_command.download_kukaj_video',
                    'data': {
                        'url': '{{ trigger.data.url }}',
                        'format': '{{ trigger.data.format | default("m3u8") }}'
                    }
                }
            },
            {
                'alias': 'Download Complete Notification',
                'trigger': {
                    'platform': 'state',
                    'entity_id': 'sensor.kukaj_downloads'
                },
                'action': {
                    'service': 'notify.persistent_notification',
                    'data': {
                        'message': 'Video download completed! {{ states("sensor.kukaj_downloads") }} files ready.'
                    }
                }
            }
        ]
    }
    
    return config

def save_config(config, filename='ha_config.yaml'):
    """Save configuration to YAML file."""
    with open(filename, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"✅ Configuration saved to {filename}")

def print_instructions():
    """Print setup instructions."""
    print("""
🏠 Home Assistant Integration Setup Complete!

📋 Next Steps:

1. Copy the contents of 'ha_config.yaml' to your Home Assistant configuration.yaml
2. Restart Home Assistant
3. Start your Kukaj downloader: python3 start_web.py
4. Test the integration:

   # Download via service call
   service: rest_command.download_kukaj_video
   data:
     url: "https://serial.kukaj.fi/hra-na-olihen/S03E04"
     format: "mp4"

   # Check downloads sensor
   {{ states('sensor.kukaj_downloads') }} files ready

5. Create webhook for external access:
   curl -X POST http://homeassistant.local:8123/api/webhook/kukaj_download \\
     -H 'Content-Type: application/json' \\
     -d '{"url": "https://serial.kukaj.fi/hra-na-olihen/S03E04", "format": "mp4"}'

🎯 Features Available:
- ✅ Web interface at http://localhost:8080
- ✅ REST API for automations
- ✅ Shell commands for direct CLI
- ✅ Webhook support for external apps
- ✅ Download monitoring sensor
- ✅ Automatic cleanup automation

🚀 No changes to your existing code required!
""")

if __name__ == "__main__":
    print("🔧 Setting up Home Assistant integration...")
    
    # Generate configuration
    config = generate_ha_config()
    
    # Save to file
    save_config(config)
    
    # Print instructions
    print_instructions()
    
    print("🎉 Setup complete! Check ha_config.yaml for your configuration.") 