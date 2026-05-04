#!/usr/bin/env python3
"""
工作台 - Web应用启动器
提供轻量化 Web 入口
"""

import asyncio
import logging
import sys
import argparse
import importlib
from typing import Optional


class TelegramMonitorWebApp:
    
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, skip_config_check: bool = False):
        from core import AccountManager, MonitorEngine
        from core.log import get_logger
        from web.app import WebApp
        from web.status import StatusMonitor

        try:
            from core.config import config
            self.config = config
        except Exception as e:
            print(f"⚠️  配置模块加载失败: {e}")
            self.config = None
            if not skip_config_check:
                return
        
        self.host = host or (self.config.WEB_HOST if self.config else "127.0.0.1")
        self.port = port or (self.config.WEB_PORT if self.config else 8000)
        self.logger = get_logger(__name__)
        
        if not skip_config_check:
            self.check_configuration()
        
        self.web_app = WebApp()
        self.status_monitor = StatusMonitor()
        self.account_manager = AccountManager()
        self.monitor_engine = MonitorEngine()
        
        self.app = self.web_app.get_app()
        
        self.setup_config_routes()
        
        self.logger.info(f"Web应用初始化完成，地址: http://{self.host}:{self.port}")

    def check_configuration(self):
        if not self.config:
            self.logger.error("配置模块未加载")
            return False
        
        if not self.config.is_telegram_configured():
            self.logger.warning("接口未配置")
            return False
        
        self.logger.info("配置检查通过")
        return True

    def setup_config_routes(self):
        @self.app.get("/config/status")
        async def config_status():
            if not self.config:
                return {"error": "配置模块未加载"}
            
            return {
                "telegram_configured": self.config.is_telegram_configured(),
                "openai_configured": self.config.is_openai_configured(),
                "email_configured": bool(self.config.EMAIL_USERNAME and self.config.EMAIL_PASSWORD)
            }
        
        @self.app.get("/config/validate")
        async def validate_config():
            if not self.config:
                return {"valid": False, "message": "配置模块未加载"}
            
            return {"valid": self.config.validate_config()}

    def get_app(self):
        return self.app

    def run(self):
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            self.logger.info("收到退出信号，正在关闭Web应用...")
        except Exception as e:
            self.logger.error(f"Web应用运行异常: {e}")
            raise

    async def run_async(self):
        try:
            import uvicorn

            self.logger.info("正在启动监控引擎...")
            await self.monitor_engine.start()
            self.logger.info("监控引擎启动完成")
            
            await self.web_app.start_background_tasks()
            
            config_uvicorn = uvicorn.Config(
                app=self.app,
                host=self.host,
                port=self.port,
                log_level="error",
                access_log=False,
                reload=self.config and self.config.WEB_DEBUG,
                proxy_headers=True,
                forwarded_allow_ips="*",
                timeout_keep_alive=5,
                timeout_graceful_shutdown=10
            )
            
            server = uvicorn.Server(config_uvicorn)
            
            self.logger.info("正在启动Web服务器...")
            self.logger.info("="*60)
            self.logger.info(f"🌐 Web界面地址: http://{self.host}:{self.port}")
            self.logger.info(f"📊 仪表板: http://{self.host}:{self.port}/")
            self.logger.info(f"⚙️  新建规则: http://{self.host}:{self.port}/wizard")
            self.logger.info(f"📚 API文档: http://{self.host}:{self.port}/docs")
            
            if self.config:
                config_status = self.config.get_status()
                self.logger.info("")
                self.logger.info("📋 功能状态:")
                self.logger.info(f"   接口: {'✅ 已配置' if config_status['telegram_configured'] else '❌ 未配置'}")
                self.logger.info(f"   AI监控:   {'✅ 可用' if config_status['openai_configured'] else '⚠️  不可用'}")
                self.logger.info(f"   邮件通知: {'✅ 可用' if config_status['email_configured'] else '⚠️  不可用'}")
            
            self.logger.info("="*60)
            
            await server.serve()
            
        except Exception as e:
            self.logger.error(f"Web应用启动失败: {e}")
            raise


def check_config_only():
    try:
        from core.config import config
        print("✅ 配置模块加载成功")
        
        if config.is_telegram_configured():
            print("✅ 接口 已配置")
        else:
            print("❌ 接口 未配置")
            
        if config.is_openai_configured():
            print("✅ OpenAI API 已配置")
        else:
            print("⚠️  OpenAI API 未配置（AI功能不可用）")
            
        if config.EMAIL_USERNAME and config.EMAIL_PASSWORD:
            print("✅ 邮件配置已设置")
        else:
            print("⚠️  邮件配置未设置（邮件通知不可用）")
            
        return config.validate_config()
        
    except Exception as e:
        print(f"❌ 配置检查失败: {e}")
        return False


def check_imports_only():
    modules = [
        "uvicorn",
        "fastapi",
        "telethon",
        "core.account",
        "core.config",
        "core.engine",
        "core.forward",
        "core.model",
        "monitor.factory",
        "web.app",
        "web.wizard",
    ]

    ok = True
    print("🔧 检查模块导入...")
    for module in modules:
        try:
            importlib.import_module(module)
            print(f"✅ {module}")
        except Exception as e:
            ok = False
            print(f"❌ {module}: {e}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="工作台 Web界面")
    parser.add_argument("--host", help="绑定主机地址")
    parser.add_argument("--port", type=int, help="绑定端口")
    parser.add_argument("--public", action="store_true", help="允许外部访问 (绑定到 0.0.0.0)")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    parser.add_argument("--check-config", action="store_true", help="仅检查配置不启动服务")
    parser.add_argument("--check-imports", action="store_true", help="检查模块导入")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        from core.log import get_default_logger
        default_logger = get_default_logger()
        default_logger.setLevel(logging.DEBUG)
        for handler in default_logger.handlers:
            handler.setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)
    
    if args.check_imports:
        sys.exit(0 if check_imports_only() else 1)
    
    if args.check_config:
        success = check_config_only()
        sys.exit(0 if success else 1)
    
    host = args.host
    if args.public:
        host = "0.0.0.0"
        print("⚠️  警告: 启用公共访问模式，Web界面将对外网开放")
        print("⚠️  请确保在安全的网络环境中使用")
        
        try:
            confirm = input("是否继续? (y/N): ").lower().strip()
            if confirm not in ('y', 'yes'):
                print("已取消启动")
                return
        except KeyboardInterrupt:
            print("\n已取消启动")
            return
    
    try:
        app = TelegramMonitorWebApp(host=host, port=args.port)
        app.run()
    except Exception as e:
        print(f"启动失败: {e}")
        print("\n💡 提示:")
        print("1. 检查是否已正确配置 .env 文件")
        print("2. 运行 'python app.py --check-config' 检查配置")
        print("3. 运行 'python app.py --check-imports' 检查模块导入")
        print("4. 查看日志获取详细错误信息")
        sys.exit(1)


if __name__ == "__main__":
    main()
