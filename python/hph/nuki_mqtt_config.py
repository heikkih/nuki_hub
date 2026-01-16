import argparse
import json
import time
import sys
import paho.mqtt.client as mqtt
import urllib.request
import urllib.error

# Default MQTT settings
DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
BASE_TOPIC = "nuki/hub"

# Topic definitions
TOPIC_ACTION_SUFFIX = "/configuration/action"
TOPIC_RESULT_SUFFIX = "/configuration/commandResult"

# Configuration definitions
LOCK_CONFIG_KEYS = {
    "basic": [
        "name", "latitude", "longitude", "autoUnlatch", "pairingEnabled", 
        "buttonEnabled", "ledEnabled", "ledBrightness", "timeZoneOffset", 
        "dstMode", "fobAction1", "fobAction2", "fobAction3", "singleLock", 
        "advertisingMode", "timeZone"
    ],
    "advanced": [
        "unlockedPositionOffsetDegrees", "lockedPositionOffsetDegrees", 
        "singleLockedPositionOffsetDegrees", "unlockedToLockedTransitionOffsetDegrees", 
        "lockNgoTimeout", "singleButtonPressAction", "doubleButtonPressAction", 
        "detachedCylinder", "batteryType", "automaticBatteryTypeDetection", 
        "unlatchDuration", "autoLockTimeOut", "autoUnLockDisabled", 
        "nightModeEnabled", "nightModeStartTime", "nightModeEndTime", 
        "nightModeAutoLockEnabled", "nightModeAutoUnlockDisabled", 
        "nightModeImmediateLockOnStart", "autoLockEnabled", 
        "immediateAutoLockEnabled", "autoUpdateEnabled", "rebootNuki", 
        "motorSpeed", "enableSlowSpeedDuringNightMode", "recalibrateNuki"
    ]
}

OPENER_CONFIG_KEYS = {
    "basic": [
        "name", "latitude", "longitude", "pairingEnabled", "buttonEnabled", 
        "ledFlashEnabled", "timeZoneOffset", "dstMode", "fobAction1", 
        "fobAction2", "fobAction3", "operatingMode", "advertisingMode", "timeZone"
    ],
    "advanced": [
        "intercomID", "busModeSwitch", "shortCircuitDuration", 
        "electricStrikeDelay", "randomElectricStrikeDelay", 
        "electricStrikeDuration", "disableRtoAfterRing", "rtoTimeout", 
        "doorbellSuppression", "doorbellSuppressionDuration", "soundRing", 
        "soundOpen", "soundRto", "soundCm", "soundConfirmation", "soundLevel", 
        "singleButtonPressAction", "doubleButtonPressAction", "batteryType", 
        "automaticBatteryTypeDetection", "rebootNuki", "recalibrateNuki"
    ]
}

HUB_CONFIG_KEYS = [
    # Network
    "dhcpena", "ipaddr", "ipsub", "ipgtw", "dnssrv", "hostname", "wifiSSID", "wifiPass", 
    # MQTT
    "mqttlog", "mqtt_lock_path", 
    # Auth & Security
    "authmaxentry", "authInfoEna", "authPerEntry", "cred_user", "cred_password",
    "kpmaxentry", "kpInfoEnabled", "kpPerEntry", "kpPubCode",
    "tcmaxentry", "tcPerEntry", "tcInfoEnabled",
    "pubAuth", "cnfInfoEnabled",
    # Intervals & Timeouts
    "lockStInterval", "configInterval", "batInterval", "kpInterval", 
    "nrRetry", "rtryDelay", "hybridTimer", "rssipb", "nettmout",
    # Other
    "regAsApp", "regOpnAsApp", "bleTxPwr", "checkupdates", "openercont",
    "webserver_enabled"
]

class NukiConfigClient:
    def __init__(self, broker, port, username=None, password=None, base_topic=BASE_TOPIC):
        self.broker = broker
        self.port = port
        self.base_topic = base_topic
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        
        if username and password:
            self.client.username_pw_set(username, password)
            
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.response = None
        self.waiting_for_topic = None
        self.ip_address = None

    def on_connect(self, client, userdata, flags, rc, properties):
        if rc == 0:
            print(f"Connected to MQTT broker at {self.broker}:{self.port}")
        else:
            print(f"Failed to connect, return code {rc}")

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode("utf-8")
        
        if topic.endswith("/info/nukiHubIp"):
            self.ip_address = payload
            return
        
        if self.waiting_for_topic and topic == self.waiting_for_topic:
            # Ignore the "initialization" messages or reset messages usually containing "--"
            if payload == "--":
                return
            
            try:
                self.response = json.loads(payload)
            except json.JSONDecodeError:
                self.response = payload
                
            print(f"\nReceived response on {topic}:")
            print(json.dumps(self.response, indent=2) if isinstance(self.response, dict) else self.response)

    def connect(self):
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()
        time.sleep(1) # Give it a moment to connect

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def update_config(self, target, config_dict, timeout=10):
        """
        target: 'hub', 'lock', or 'opener'
        config_dict: Dictionary of settings to update
        """
        if target == 'hub':
            topic_base = self.base_topic
        elif target == 'lock':
            topic_base = f"{self.base_topic}/lock"
        elif target == 'opener':
            topic_base = f"{self.base_topic}/opener"
        else:
            raise ValueError("Target must be 'hub', 'lock', or 'opener'")

        action_topic = f"{topic_base}{TOPIC_ACTION_SUFFIX}"
        result_topic = f"{topic_base}{TOPIC_RESULT_SUFFIX}"

        self.waiting_for_topic = result_topic
        self.response = None
        
        # Subscribe to result topic
        self.client.subscribe(result_topic)
        
        payload = json.dumps(config_dict)
        print(f"Sending config to {action_topic}: {payload}")
        
        self.client.publish(action_topic, payload)

        start_time = time.time()
        while self.response is None:
            if time.time() - start_time > timeout:
                print("Timeout waiting for response.")
                break
            time.sleep(0.1)
            
        self.client.unsubscribe(result_topic)
        return self.response

    def wait_for_ip(self, timeout=10):
        ip_topic = f"{self.base_topic}/info/nukiHubIp"
        print(f"Subscribing to {ip_topic} to get IP...")
        self.client.subscribe(ip_topic)
        
        start_time = time.time()
        while self.ip_address is None:
            if time.time() - start_time > timeout:
                return None
            time.sleep(0.1)
        
        self.client.unsubscribe(ip_topic)
        return self.ip_address

def fetch_coredump(client, web_user, web_password, output_file):
    print("Waiting for Nuki Hub IP address...")
    ip = client.wait_for_ip()
    if not ip:
        print("Timeout waiting for IP address. Ensure Nuki Hub is online and MQTT is connected.")
        return

    print(f"Nuki Hub IP: {ip}")
    url = f"http://{ip}/get?page=coredump"
    
    # Setup Auth
    if web_user and web_password:
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, url, web_user, web_password)
        handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
        opener = urllib.request.build_opener(handler)
        urllib.request.install_opener(opener)

    try:
        print(f"Downloading coredump from {url}...")
        with urllib.request.urlopen(url) as response:
            data = response.read()
            # Check for 404/error text content if status 200 (since some simple servers return 200 with error html)
            # But PsychicRequest sends 404 status code (see WebCfgServer.cpp)
            # so HTTPError catch should handle it.
            
            with open(output_file, 'wb') as f:
                f.write(data)
            print(f"Coredump saved to {output_file}")
            
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("Coredump not found on device.")
        elif e.code == 401:
            print("Authentication failed. Please check --web-user and --web-password.")
        else:
            print(f"HTTP Error: {e.code} {e.reason}")
    except Exception as e:
        print(f"Error fetching coredump: {e}")

def main():
    parser = argparse.ArgumentParser(description="Nuki Hub MQTT Configuration Client")
    parser.add_argument("--broker", default=DEFAULT_BROKER, help="MQTT Broker IP")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MQTT Broker Port")
    parser.add_argument("--user", help="MQTT Username")
    parser.add_argument("--password", help="MQTT Password")
    parser.add_argument("--topic", default=BASE_TOPIC, help="Base topic for Nuki Hub (default: nukihub)")
    parser.add_argument("--list-settings", action="store_true", help="List all available settings for a target")
    parser.add_argument("--fetch-coredump", action="store_true", help="Fetch coredump from Nuki Hub")
    parser.add_argument("--web-user", help="Web Interface Username (if auth enabled)")
    parser.add_argument("--web-password", help="Web Interface Password (if auth enabled)")
    parser.add_argument("--output", default="coredump.hex", help="Output file for coredump")
    
    parser.add_argument("target", choices=['hub', 'lock', 'opener'], nargs='?', help="Target device to configure")
    parser.add_argument("settings", nargs='*', help="Settings in key=value format (e.g. name=MyLock ledBrightness=2)")

    args = parser.parse_args()

    # Coredump fetch
    if args.fetch_coredump:
        client = NukiConfigClient(args.broker, args.port, args.user, args.password, args.topic)
        try:
            client.connect()
            fetch_coredump(client, args.web_user, args.web_password, args.output)
        except KeyboardInterrupt:
            print("Interrupted")
        finally:
            client.disconnect()
        sys.exit(0)

    if not args.target:
        print("Error: Target is required unless usage --fetch-coredump.")
        parser.print_help()
        sys.exit(1)

    # List settings helper
    if args.list_settings:
        print(f"--- Available settings for {args.target} ---")
        if args.target == 'lock':
            print("\n[Basic]")
            for k in sorted(LOCK_CONFIG_KEYS['basic']): print(f"  {k}")
            print("\n[Advanced]")
            for k in sorted(LOCK_CONFIG_KEYS['advanced']): print(f"  {k}")
        elif args.target == 'opener':
            print("\n[Basic]")
            for k in sorted(OPENER_CONFIG_KEYS['basic']): print(f"  {k}")
            print("\n[Advanced]")
            for k in sorted(OPENER_CONFIG_KEYS['advanced']): print(f"  {k}")
        elif args.target == 'hub':
            print("\n[Hub Settings]")
            for k in sorted(HUB_CONFIG_KEYS): print(f"  {k}")
        sys.exit(0)
    
    if not args.settings:
        print("Error: No settings provided. Use --list-settings to see available options.")
        sys.exit(1)

    # Validate keys
    valid_keys = []
    if args.target == 'lock':
        valid_keys = LOCK_CONFIG_KEYS['basic'] + LOCK_CONFIG_KEYS['advanced']
    elif args.target == 'opener':
        valid_keys = OPENER_CONFIG_KEYS['basic'] + OPENER_CONFIG_KEYS['advanced']
    elif args.target == 'hub':
        valid_keys = HUB_CONFIG_KEYS

    # Parse settings into a dictionary
    config_data = {}
    for setting in args.settings:
        if "=" in setting:
            key, value = setting.split("=", 1)
            
            # Key validation
            if args.target != 'hub': # Hub keys are less strict in my list, but useful to warn
                if key not in valid_keys:
                    print(f"Warning: '{key}' might not be a valid setting for {args.target}")

            # Try to convert to int if possible, as Nuki Hub expects correct types often
            try:
                config_data[key] = int(value)
            except ValueError:
                if value.lower() == "true":
                    config_data[key] = True
                elif value.lower() == "false":
                    config_data[key] = False
                else:
                    config_data[key] = value
        else:
            print(f"Ignored invalid setting '{setting}'. Must be key=value")

    if not config_data:
        print("No valid settings provided.")
        sys.exit(1)

    client = NukiConfigClient(args.broker, args.port, args.user, args.password, args.topic)
    
    try:
        client.connect()
        client.update_config(args.target, config_data)
    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
