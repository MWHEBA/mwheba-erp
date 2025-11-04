"""
Biometric Bridge Agent
يعمل على جهاز محلي ويربط السيرفر بماكينة البصمة بشكل آمن
"""
import os
import sys
import time
import json
import logging
import requests
from datetime import datetime
from zk import ZK
import schedule

# إعدادات
CONFIG_FILE = 'config.json'
LOG_FILE = 'bridge_agent.log'

# إعداد الـ Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BiometricBridgeAgent:
    """وكيل الاتصال بين السيرفر وماكينة البصمة"""
    
    def __init__(self, config_path=CONFIG_FILE):
        """تحميل الإعدادات"""
        self.config = self.load_config(config_path)
        self.device_ip = self.config.get('device_ip')
        self.device_port = self.config.get('device_port', 4370)
        self.server_url = self.config.get('server_url')
        self.agent_code = self.config.get('agent_code')
        self.agent_secret = self.config.get('agent_secret')
        self.sync_interval = self.config.get('sync_interval', 5)  # دقائق
        self.last_sync_time = None
        
        logger.info(f"Bridge Agent initialized - Code: {self.agent_code}")
    
    def load_config(self, config_path):
        """تحميل ملف الإعدادات"""
        if not os.path.exists(config_path):
            logger.error(f"Config file not found: {config_path}")
            self.create_default_config(config_path)
            logger.info(f"Created default config file. Please edit: {config_path}")
            sys.exit(1)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def create_default_config(self, config_path):
        """إنشاء ملف إعدادات افتراضي"""
        default_config = {
            "device_ip": "192.168.1.100",
            "device_port": 4370,
            "server_url": "https://yoursite.com",
            "agent_code": "AGENT-001",
            "agent_secret": "your-secret-key-here",
            "sync_interval": 5,
            "auto_discover_ip": True
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
    
    def discover_device_ip(self):
        """
        اكتشاف IP الماكينة تلقائياً في الشبكة المحلية
        يبحث في نطاق 192.168.1.1 - 192.168.1.254
        """
        logger.info("Searching for ZKTeco device in local network...")
        
        import socket
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def check_ip(ip):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex((ip, self.device_port))
                sock.close()
                if result == 0:
                    return ip
            except:
                pass
            return None
        
        # البحث في الشبكة المحلية
        base_ip = "192.168.1."
        ips_to_check = [f"{base_ip}{i}" for i in range(1, 255)]
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = {executor.submit(check_ip, ip): ip for ip in ips_to_check}
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    logger.info(f"Found device at: {result}")
                    return result
        
        logger.warning("No device found in network")
        return None
    
    def test_connection(self):
        """اختبار الاتصال بالماكينة"""
        try:
            logger.info(f"Testing connection to {self.device_ip}:{self.device_port}")
            
            conn = ZK(self.device_ip, port=self.device_port, timeout=5)
            zk = conn.connect()
            
            device_name = zk.get_device_name()
            firmware = zk.get_firmware_version()
            users_count = len(zk.get_users())
            
            zk.disconnect()
            
            logger.info(f"✓ Connected successfully!")
            logger.info(f"  Device: {device_name}")
            logger.info(f"  Firmware: {firmware}")
            logger.info(f"  Users: {users_count}")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Connection failed: {e}")
            return False
    
    def get_attendance_records(self, from_timestamp=None):
        """جلب سجلات الحضور من الماكينة"""
        try:
            conn = ZK(self.device_ip, port=self.device_port, timeout=5)
            zk = conn.connect()
            
            attendances = zk.get_attendance()
            
            # تحويل للـ JSON
            records = []
            for att in attendances:
                # فلترة حسب الوقت إذا تم تحديده
                if from_timestamp and att.timestamp < from_timestamp:
                    continue
                
                records.append({
                    'user_id': str(att.user_id),
                    'timestamp': att.timestamp.isoformat(),
                    'status': att.status if hasattr(att, 'status') else 0,
                    'punch': att.punch if hasattr(att, 'punch') else 0
                })
            
            zk.disconnect()
            
            logger.info(f"Fetched {len(records)} records from device")
            return records
            
        except Exception as e:
            logger.error(f"Error fetching records: {e}")
            return []
    
    def send_to_server(self, records):
        """إرسال السجلات للسيرفر"""
        if not records:
            logger.info("No new records to send")
            return True
        
        try:
            api_url = f"{self.server_url}/api/biometric/bridge-sync/"
            
            payload = {
                'agent_code': self.agent_code,
                'records': records,
                'timestamp': datetime.now().isoformat()
            }
            
            headers = {
                'Authorization': f'Bearer {self.agent_secret}',
                'Content-Type': 'application/json'
            }
            
            logger.info(f"Sending {len(records)} records to server...")
            
            response = requests.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✓ Server response: {result.get('message')}")
                logger.info(f"  Processed: {result.get('processed', 0)}")
                logger.info(f"  Skipped: {result.get('skipped', 0)}")
                return True
            else:
                logger.error(f"✗ Server error: {response.status_code}")
                logger.error(f"  Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending to server: {e}")
            return False
    
    def sync_now(self):
        """تنفيذ المزامنة الآن"""
        logger.info("=" * 60)
        logger.info("Starting sync cycle...")
        
        try:
            # جلب السجلات من الماكينة
            records = self.get_attendance_records(self.last_sync_time)
            
            # إرسال للسيرفر
            if records:
                success = self.send_to_server(records)
                if success:
                    self.last_sync_time = datetime.now()
                    logger.info(f"✓ Sync completed successfully")
                else:
                    logger.warning("✗ Sync failed - will retry next cycle")
            else:
                logger.info("No new records to sync")
            
        except Exception as e:
            logger.error(f"Sync error: {e}")
        
        logger.info("=" * 60)
    
    def run(self):
        """تشغيل الوكيل"""
        logger.info("=" * 60)
        logger.info("Biometric Bridge Agent Started")
        logger.info(f"Agent Code: {self.agent_code}")
        logger.info(f"Device: {self.device_ip}:{self.device_port}")
        logger.info(f"Server: {self.server_url}")
        logger.info(f"Sync Interval: {self.sync_interval} minutes")
        logger.info("=" * 60)
        
        # اختبار الاتصال بالماكينة
        if not self.test_connection():
            logger.error("Cannot connect to device. Please check configuration.")
            
            # محاولة اكتشاف IP تلقائياً
            if self.config.get('auto_discover_ip', False):
                discovered_ip = self.discover_device_ip()
                if discovered_ip:
                    self.device_ip = discovered_ip
                    logger.info(f"Updated device IP to: {discovered_ip}")
                    # حفظ في الإعدادات
                    self.config['device_ip'] = discovered_ip
                    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                        json.dump(self.config, f, indent=4, ensure_ascii=False)
                else:
                    logger.error("Auto-discovery failed. Exiting...")
                    return
        
        # مزامنة فورية عند البدء
        self.sync_now()
        
        # جدولة المزامنة الدورية
        schedule.every(self.sync_interval).minutes.do(self.sync_now)
        
        logger.info(f"Scheduled sync every {self.sync_interval} minutes")
        logger.info("Press Ctrl+C to stop")
        
        # حلقة التشغيل الرئيسية
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\nShutting down gracefully...")
            logger.info("Bridge Agent stopped")


def main():
    """نقطة البداية"""
    try:
        print("""
        ╔══════════════════════════════════════════════════════════╗
        ║         Biometric Bridge Agent v1.0                      ║
        ║         Secure connection between ZKTeco & Server        ║
        ╚══════════════════════════════════════════════════════════╝
        """)
    except UnicodeEncodeError:
        # Fallback for Windows Service console encoding issues
        print("=" * 60)
        print("    Biometric Bridge Agent v1.0")
        print("    Secure connection between ZKTeco & Server")
        print("=" * 60)
    
    agent = BiometricBridgeAgent()
    agent.run()


if __name__ == "__main__":
    main()
