# Cisco DHCP to Unix dnsmasq and Fortinet DNS Configuration Converter

## Description

This script automates the process of converting Cisco DHCP configurations into Unix-style host files for use with dnsmasq, and then writing DNS entries into a Fortinet firewall DNS database.

### Usage
Once you have the required configuration in place, you can run the script by executing the following command in your terminal:

```bash
python cisco_dhcp_to_dns.py
```
## Functions Overview

The script includes the following functions:

- `load_config`: Loads the YAML configuration file.
- `initialize_logging`: Initializes the logging configuration.
- `ssh_connect`: Establishes an SSH connection to a Cisco device.
- `retrieve_dhcp_pool_config`: Retrieves the DHCP pool configuration from a Cisco device.
- `read_existing_host_file`: Reads the existing Unix-style host file.
- `convert_to_host_file`: Converts the DHCP configuration into a host file format.
- `write_to_file`: Writes content to a file.
- `execute_unix_commands`: Executes Unix commands (e.g., `chown`, `chgrp`, `restart`).
- `send_command`: Sends a command to an SSH shell.
- `configure_fortinet_dns`: Configures Fortinet DNS settings.
- `parse_host_file`: Parses the host file content.
- `write_dns_to_fortinet`: Writes parsed DNS entries to the Fortinet firewall.

### Key Notes
- The script is modular and can be easily modified for different devices, commands, or configurations.
- The use of SSH for configuration retrieval and command execution allows for automation in network management tasks.
- The script handles both IPv4 and IPv6 configurations, ensuring compatibility with modern DNS infrastructures.

## Installation

### Prerequisites

To use this script, you need the following:
- Python 3.x installed.
- The following Python libraries:
  - `paramiko` for SSH communication.
  - `yaml` for YAML file parsing.
  - `requests` for making HTTP requests.
  - `logging`, `subprocess`, `time`, and other standard Python libraries.
  
You can install the required Python libraries using `pip`:

```bash
pip install paramiko pyyaml requests
```

### Configuration
Before running the script, you must create a YAML configuration file (config.yaml). The YAML file should include the following sections:

```yaml
logging:
  level: DEBUG  # Options: DEBUG, INFO, WARNING, ERROR

timeouts:
  short: 1
  medium: 5
  long: 10

cisco_device:
  hostname: "<Cisco device IP>"
  username: "<SSH username>"
  password: "<SSH password>"
  port: 22  # Optional: Change if non-standard port is used

fortinet_config:
  hostname: "<Fortinet firewall IP>"
  username: "<Fortinet username>"
  password: "<Fortinet password>"
  port: 22  # Optional: Change if non-standard port is used
  base_name: "<Database base name>"
  ttl: 3600
  primary_dns: "a.root-servers.net"
  contact: "hostmaster@webserver.com"
  
dnsdomain: "<Your DNS domain>"
```

## Process Overview
1. Cisco Device Connection: The script connects to a Cisco device using SSH and retrieves the DHCP configuration.
1. Conversion to Unix Host File: The DHCP configuration is parsed and converted to a Unix-style host file format.
1. Restarting Unix processes such as Pi-hole to re-read the hostfile.
1. Making an API call via webhooks to update DNS (i.e., for Pi-hole v6).
1. Writing to DNS Database: DNS entries are parsed and written into a Fortinet firewall DNS database via SSH.

## Acknowledgements
* Paramiko: This script uses Paramiko for SSH connectivity to the Cisco device and Fortinet firewall.
* YAML: Used for configuration file parsing to load settings.
* Requests: Used for sending PATCH requests to a remote server to update DNS configuration.
* Special thanks to the creators of these libraries and to the open-source community for providing these powerful tools.

## License
This script is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
