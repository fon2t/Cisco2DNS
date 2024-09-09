"""
Author: Nick Route
Description: Cisco DHCP configuration to Unix dnsmasq and Fortinet DNS database converter

This script connects to a Cisco device to retrieve DHCP pool configurations, converts
them to a Unix-style host file for dnsmasq, and then writes DNS entries to a Fortinet firewall DNS database.

Functions:
- load_config: Loads the YAML configuration file.
- initialize_logging: Initializes the logging configuration.
- ssh_connect: Connects to a device via SSH.
- retrieve_dhcp_pool_config: Retrieves DHCP configuration from a Cisco device.
- read_existing_host_file: Reads an existing Unix-style host file.
- convert_to_host_file: Converts DHCP config into a host file format.
- write_to_file: Writes content to a file.
- execute_unix_commands: Executes Unix commands (chown, chgrp, restart).
- send_command: Sends a command to an SSH shell.
- configure_fortinet_dns: Configures Fortinet DNS settings.
- parse_host_file: Parses the host file content from memory.
- write_dns_to_fortinet: Writes parsed DNS entries to a Fortinet firewall.

Main Routine:
- Connects to a Cisco device, retrieves DHCP config, converts it to a Unix-style host file, 
  and writes the result to the output file.
- Configures DNS entries on the Fortinet firewall using the host file data.

"""
# Standard library imports
import logging
import sys
import datetime
import re
import os
import subprocess
import time

# Third-party imports
import paramiko
import yaml

###########################
# Configuration Subroutines
###########################

# Load YAML configuration file
def load_config(yaml_file):
    with open(yaml_file, 'r') as file:
        return yaml.safe_load(file)

# Initialize logging
def initialize_logging(log_level):
    level = logging.DEBUG if log_level == 'DEBUG' else logging.INFO
    logging.basicConfig(stream=sys.stderr, level=level)

###########################
# SSH Connection Subroutines
###########################

# Connect to device using ssh
def ssh_connect(hostname, username, password, port):
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname, username=username, password=password, timeout=10, port=port)
        return ssh_client
    except paramiko.AuthenticationException:
        logging.error("Authentication failed. Please check your credentials.")
        return None
    except paramiko.SSHException as e:
        logging.error(f"SSH: Error connecting to {hostname}: {e}")
        return None

# Retrieve DHCP pool configuration
def retrieve_dhcp_pool_config(ssh_client):
    try:
        logging.info("SSH: Retrieving DHCP configuration")
        stdin, stdout, stderr = ssh_client.exec_command("show running-config | include ip dhcp pool | host")
        dhcp_config = stdout.read().decode("utf-8")
        logging.info("SSH: Retrieved DHCP configuration")
        return dhcp_config
    except paramiko.SSHException as e:
        logging.error(f"SSH: Error retrieving DHCP pool configuration: {e}")
        return None

###########################
# Host File Handling
###########################

# Read the existing Unix-style host file
def read_existing_host_file(existing_file):
    try:
        with open(existing_file, 'r') as file:
            return file.read()
    except FileNotFoundError:
        return ""

# Convert DHCP config to host file format
def convert_to_host_file(dhcp_config, existing_content, dnsdomain):
    lines = dhcp_config.split('\n')
    in_dhcp_pool = False
    host_entries = []
    unix_hosts = ""

    for line in lines:
        line = line.strip()
        pool_match = re.match(r"\s*ip dhcp pool (.+)$", line)
        if pool_match:
            in_dhcp_pool = True
            pool_name = pool_match.group(1).lower()
        elif in_dhcp_pool and re.match(r"\s*host ([^\s]+) ([^\s]+)", line):
            entry = re.match(r"\s*host ([^\s]+) ([^\s]+)", line)
            ip_address, netmask = entry.group(1), entry.group(2)
            host_entries.append((ip_address, pool_name + "." + dnsdomain))
        else:
            in_dhcp_pool = False

    sorted_entries = sorted(host_entries, key=lambda x: tuple(map(int, x[0].split('.')[1:])))

    # Create file header
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"# Auto created host file \n# Generated from switch dhcp configuration \n# Generated on {now} \n"
    
    unix_hosts = header + existing_content + "\n".join([f"{ip} {hostname}" for ip, hostname in sorted_entries])

    return unix_hosts

# Writes a file to a specified directory
def write_to_file(file_path, content):
    with open(file_path, 'w', newline=os.linesep) as file:
        file.write(content)

# Runs Unix commands by parsing the directory
def execute_unix_commands(commands):
    try:
        for command_name, command in commands.items():
            if command:  # Ensure there's a command to run
                logging.info(f"Executing {command_name}: {command}")
                subprocess.run(command, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing command {command_name}: {e}")

###########################
# Fortinet DNS Configuration
###########################

# Send command to the Fortinet firewall
def send_command(shell, command):
    shell.send(command + '\n')
    time.sleep(sleep_durations['short'])  # Give some time for the command to be executed
    output = shell.recv(10000).decode('utf-8')  # Adjust buffer size as needed
    logging.info(f"Executed command: {command}")
    logging.debug(f"\nOutput: {output}")
    return output

# Configure Fortinet DNS settings
def configure_fortinet_dns(shell, fortinet_config, dnsdomain, dns_entries):
    logging.info("Starting Fortinet DNS configuration")

    # Extract Fortinet-specific values from the configuration
    dbname = fortinet_config['base_name']
    ttl = fortinet_config['ttl']
    primary_name = fortinet_config.get('primary_dns', 'a.root-servers.net')  # Default value if not in config
    contact = fortinet_config.get('contact', 'hostmaster@webserver.com')  # Default value if not in config

    # Enter configuration mode
    send_command(shell, "config system dns-database")

    # Delete current database 
    send_command(shell, f"delete \"{dbname}\"")
    time.sleep(sleep_durations['medium'])

    # Create database
    send_command(shell, f"edit \"{dbname}\"")
    # Single mega command
    send_command(shell, f"set domain \"{dnsdomain}\"\nset ttl {ttl}\nset primary-name \"{primary_name}\"\nset contact \"{contact}\"")
    # Start database configuration    
    send_command(shell, "config dns-entry")

    # Add DNS entries
    idx = 1  # Start index from 1
    for hostname, ip in dns_entries:
        # Add the forward DNS entry
        
        # Check if the IP address is IPv4 and adjust command
        if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ip):
           send_command(shell, f"edit {idx}\nset type A\nset hostname \"{hostname}\"\nset ip {ip}\nnext")
        else:
           send_command(shell, f"edit {idx}\nset type AAAA\nset hostname \"{hostname}\"\nset ipv6 {ip}\nnext")    
        
        # Increment idx again for the PTR records
        idx += 1
        
        # Check if the IP address is IPv4 and adjust PTR command
        if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ip):
           send_command(shell, f"edit {idx}\nset type PTR\nset hostname \"{hostname}\"\nset ip {ip}\nnext")
        else:
           send_command(shell, f"edit {idx}\nset type PTR_V6\nset hostname \"{hostname}\"\nset ipv6 {ip}\nnext")
  
        # Increment idx again for the next iteration
        idx += 1

    # Exit the DNS configuration with an end, next, end
    send_command(shell, "end\nnext\nend")
    logging.info("Fortinet DNS configuration complete")

def parse_host_file(host_file_content):
    dns_entries = []
    lines = host_file_content.splitlines()
    for line in lines:
        if line.strip() and not line.startswith("#"):
            parts = line.split()
            if len(parts) == 2:
                ip_address, hostname = parts
                dns_entries.append((hostname, ip_address))
    return dns_entries

# Write DNS entries to Fortinet firewall
def write_dns_to_fortinet(fortinet_config, dnsdomain, host_file_content):

    # Parse DNS entries from host file content
    dns_entries = parse_host_file(host_file_content)

    # Extract Fortinet parameters from the passed config
    fortinet_host = fortinet_config['hostname']
    fortinet_user = fortinet_config['username']
    fortinet_pass = fortinet_config['password']
    fortinet_port = fortinet_config['port']
    ttl = fortinet_config['ttl']
    dbname = fortinet_config['base_name']

    # Connect to Fortinet Firewall via SSH
    ssh_client = ssh_connect(fortinet_host, fortinet_user, fortinet_pass, fortinet_port)
    
    if ssh_client:
        try:
            # Open an interactive shell
            shell = ssh_client.invoke_shell()
            time.sleep(1)  # Wait for the shell to be ready

            # Perform DNS configuration
            configure_fortinet_dns(shell, fortinet_config, dnsdomain, dns_entries)

        except paramiko.SSHException as e:
            logging.error(f"SSH: Error writing DNS entries to Fortinet Firewall: {e}")
        finally:
            ssh_client.close()

#############################
# Main Routine
#############################
def main():
    """Main routine that handles retrieving Cisco DHCP configuration, converting it, and configuring Fortinet DNS."""
    # Load the configuration
    config = load_config("config.yaml")
    initialize_logging(config['logging']['level'])

    # Make sleep durations globally accessible within the script
    global sleep_durations
    sleep_durations = config['timeouts']

    # Step 1: SSH into the Cisco device to retrieve DHCP configuration
    ssh_client = ssh_connect(config['ssh']['hostname'], config['ssh']['username'], config['ssh']['password'], config['ssh']['port'])
    
    if ssh_client:
        dhcp_config = retrieve_dhcp_pool_config(ssh_client)
        base_host_file = read_existing_host_file(config['files']['existing_host_file'])

        if dhcp_config:
            # Step 2: Convert DHCP configuration to Unix-style host file
            host_file = convert_to_host_file(dhcp_config, base_host_file, config['dns']['domain'])
            logging.info("FUNCTION: Converted Cisco configuration to Unix style host file:\n")
            logging.debug(host_file)

            # Step 3: Write the host file to disk
            write_to_file(config['files']['output_file'], host_file)
            logging.info(f"FILEIO: Host file written to: {config['files']['output_file']}")
        
            # Step 4: Execute Unix commands (chown, chgrp, restart dnsmasq)
            execute_unix_commands(config['commands'])
            
            # Step 5: Configure DNS entries on the Fortinet Firewall
            write_dns_to_fortinet(config['fortinet'], config['dns']['domain'], host_file)

        ssh_client.close()
    


if __name__ == "__main__":
    main()
