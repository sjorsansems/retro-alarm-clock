"""
WiFi Connection Manager - Station mode (STA) met DHCP
Zorgt dat ESP32 verbindt met je WiFi netwerk en DHCP adres krijgt
"""

import network
import time

class WiFiManager:
    """Manage WiFi Station (STA) verbinding"""
    
    def __init__(self, ssid, password, timeout=10):
        """
        ssid: WiFi netwerk naam
        password: WiFi wachtwoord
        timeout: Max seconden wachten op verbinding
        """
        self.ssid = ssid
        self.password = password
        self.timeout = timeout
        self.sta = network.WLAN(network.STA_IF)
    
    def connect(self):
        """Verbind met WiFi netwerk"""
        print(f"\n=== WiFi Verbinding ===")
        print(f"Netwerk: {self.ssid}")
        
        # Zorg dat STA mode aan is
        if not self.sta.active():
            print("→ STA mode activeren...")
            self.sta.active(True)
            time.sleep(1)
        
        # Verbind met netwerk
        print(f"→ Verbinden...")
        self.sta.connect(self.ssid, self.password)
        
        # Wacht op verbinding
        start_time = time.time()
        while not self.sta.isconnected():
            elapsed = int(time.time() - start_time)
            print(f"  Wachten... ({elapsed}s)", end="\r")
            
            if elapsed > self.timeout:
                print(f"\n✗ Verbinding mislukt na {self.timeout}s")
                self.sta.disconnect()
                return False
            
            time.sleep(0.5)
        
        # Verbonden!
        ip_info = self.sta.ifconfig()
        print(f"\n✓ Verbonden!")
        print(f"  IP-adres: {ip_info[0]}")
        print(f"  Netmask:  {ip_info[1]}")
        print(f"  Gateway:  {ip_info[2]}")
        print(f"  DNS:      {ip_info[3]}")
        
        return True
    
    def disconnect(self):
        """Verbreek WiFi"""
        if self.sta.isconnected():
            self.sta.disconnect()
            print("WiFi verbroken")
    
    def is_connected(self):
        """Check of verbonden"""
        return self.sta.isconnected()
    
    def get_ip(self):
        """Get IP adres"""
        if self.is_connected():
            return self.sta.ifconfig()[0]
        return None
    
    def get_signal_strength(self):
        """Get WiFi signaal sterkte (RSSI in dBm)"""
        try:
            return self.sta.status('rssi')
        except:
            return None
    
    def scan_networks(self):
        """Scan beschikbare netwerken"""
        print("\nBeschikbare netwerken:")
        networks = self.sta.scan()
        for net in networks:
            ssid = net[0].decode('utf-8')
            rssi = net[3]  # Signal strength
            print(f"  • {ssid} (sterkte: {rssi})")
        return networks
