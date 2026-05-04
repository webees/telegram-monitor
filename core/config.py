"""
配置管理工具
处理环境变量和配置文件的读取
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from .log import get_logger

logger = get_logger(__name__)

def load_env_config():
    env_file = Path('.env')
    if env_file.exists():
        load_dotenv(env_file)
        logger.info("已加载 .env 配置文件")
    else:
        logger.warning("未找到 .env 配置文件，请复制 config.example.env 为 .env 并配置")

load_env_config()

class Config:
    
    TG_API_ID: Optional[int] = None
    TG_API_HASH: Optional[str] = None
    
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    EMAIL_SMTP_SERVER: str = "smtp.gmail.com"
    EMAIL_SMTP_PORT: int = 587
    EMAIL_USERNAME: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    EMAIL_FROM: Optional[str] = None
    EMAIL_TO: Optional[str] = None
    
    WEB_HOST: str = "127.0.0.1"
    WEB_PORT: int = 8000
    WEB_DEBUG: bool = False
    WEB_USERNAME: str = "admin"
    WEB_PASSWORD: str = "admin123"
    
    DATA_DIR: str = "./data"
    LOGS_DIR: str = "./logs"
    DOWNLOADS_DIR: str = "./data/dl"
    
    
    def __init__(self):
        self.load_from_env()
        self.create_directories()
        self.validate_config()
    
    def load_from_env(self):
        def env(name, default=None):
            value = os.getenv(name, "").strip()
            return value if value else default

        def env_int(name, default):
            value = env(name)
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                logger.error(f"{name} 必须是数字")
                return default

        if env('TG_API_ID'):
            try:
                self.TG_API_ID = int(env('TG_API_ID'))
            except ValueError:
                logger.error("TG_API_ID 必须是数字")
        
        self.TG_API_HASH = env('TG_API_HASH')
        
        self.OPENAI_API_KEY = env('OPENAI_API_KEY')
        self.OPENAI_MODEL = env('OPENAI_MODEL', self.OPENAI_MODEL)
        self.OPENAI_BASE_URL = env('OPENAI_BASE_URL', self.OPENAI_BASE_URL)
        self.EMAIL_SMTP_SERVER = env('EMAIL_SMTP_SERVER', self.EMAIL_SMTP_SERVER)
        self.EMAIL_SMTP_PORT = env_int('EMAIL_SMTP_PORT', self.EMAIL_SMTP_PORT)
        self.EMAIL_USERNAME = env('EMAIL_USERNAME')
        self.EMAIL_PASSWORD = env('EMAIL_PASSWORD')
        self.EMAIL_FROM = env('EMAIL_FROM')
        self.EMAIL_TO = env('EMAIL_TO')
        
        self.WEB_HOST = env('WEB_HOST', self.WEB_HOST)
        self.WEB_PORT = env_int('WEB_PORT', self.WEB_PORT)
        self.WEB_DEBUG = env('WEB_DEBUG', 'false').lower() == 'true'
        self.WEB_USERNAME = env('WEB_USERNAME', self.WEB_USERNAME)
        self.WEB_PASSWORD = env('WEB_PASSWORD', self.WEB_PASSWORD)
        
        self.DATA_DIR = env('DATA_DIR', self.DATA_DIR)
        self.LOGS_DIR = env('LOGS_DIR', self.LOGS_DIR)
        self.DOWNLOADS_DIR = env('DOWNLOADS_DIR', self.DOWNLOADS_DIR)
        
    
    def create_directories(self):
        directories = [self.DATA_DIR, self.LOGS_DIR, self.DOWNLOADS_DIR]
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
    
    def validate_config(self):
        warnings = []
        errors = []
        
        if not self.TG_API_ID:
            errors.append("TG_API_ID 未配置，请在 .env 文件中设置")
        
        if not self.TG_API_HASH:
            errors.append("TG_API_HASH 未配置，请在 .env 文件中设置")
        
        if not self.OPENAI_API_KEY:
            warnings.append("OPENAI_API_KEY 未配置，AI监控功能将不可用")
        
        if not self.EMAIL_USERNAME or not self.EMAIL_PASSWORD:
            warnings.append("邮件配置未完整，邮件通知功能将不可用")
        
        for warning in warnings:
            logger.warning(warning)
        
        for error in errors:
            logger.error(error)
        
        if errors:
            logger.error("配置验证失败，请检查 .env 文件")
            return False
        
        logger.info("配置验证通过")
        return True
    
    def is_telegram_configured(self) -> bool:
        return self.TG_API_ID is not None and self.TG_API_HASH is not None
    
    def is_openai_configured(self) -> bool:
        return self.OPENAI_API_KEY is not None
    
    def is_email_configured(self) -> bool:
        return all([
            self.EMAIL_USERNAME,
            self.EMAIL_PASSWORD,
            self.EMAIL_FROM
        ])
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "telegram_configured": self.is_telegram_configured(),
            "openai_configured": self.is_openai_configured(),
            "email_configured": self.is_email_configured(),
            "web_host": self.WEB_HOST,
            "web_port": self.WEB_PORT,
            "data_dir": self.DATA_DIR,
            "logs_dir": self.LOGS_DIR,
            "downloads_dir": self.DOWNLOADS_DIR
        }

config = Config()
