"""
多渠道 Webhook 通知服务
支持钉钉、企业微信、飞书机器人
"""
import json
import logging
import time
import hmac
import hashlib
import base64
from urllib.parse import quote_plus
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import requests


@dataclass
class WebhookConfig:
    """Webhook 配置"""
    platform: str = ""  # dingtalk / wecom / feishu
    webhook_url: str = ""
    secret: str = ""  # 签名密钥（钉钉/飞书）
    is_active: bool = False
    notify_on_complete: bool = True  # 扫描完成通知
    notify_on_high_risk: bool = True  # 高危端口通知


class WebhookNotifier:
    """多渠道 Webhook 通知器"""

    PLATFORMS = {
        'dingtalk': '钉钉',
        'wecom': '企业微信',
        'feishu': '飞书',
    }

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("WebhookNotifier")
        self.configs: Dict[str, WebhookConfig] = {}

    def add_config(self, platform: str, config: WebhookConfig):
        """添加平台配置"""
        config.platform = platform
        self.configs[platform] = config

    def remove_config(self, platform: str):
        """移除平台配置"""
        self.configs.pop(platform, None)

    def send_scan_result(self, scan_info: Dict) -> Dict[str, Tuple[bool, str]]:
        """
        向所有活跃平台发送扫描结果通知
        
        Args:
            scan_info: {
                'total_hosts': int,
                'open_ports': int,
                'high_risk_count': int,
                'duration': str,
                'scan_time': str,
                'report_url': str (optional)
            }
        Returns:
            {platform: (success, message)}
        """
        results = {}
        for platform, config in self.configs.items():
            if not config.is_active:
                continue
            if not config.webhook_url:
                continue

            try:
                success, msg = self._send_to_platform(platform, config, scan_info)
                results[platform] = (success, msg)
            except Exception as e:
                self.logger.error(f"[{platform}] 发送通知失败: {e}")
                results[platform] = (False, str(e))

        return results

    def _send_to_platform(self, platform: str, config: WebhookConfig, 
                          scan_info: Dict) -> Tuple[bool, str]:
        """发送到指定平台"""
        if platform == 'dingtalk':
            return self._send_dingtalk(config, scan_info)
        elif platform == 'wecom':
            return self._send_wecom(config, scan_info)
        elif platform == 'feishu':
            return self._send_feishu(config, scan_info)
        else:
            return False, f"不支持的平台: {platform}"

    def _send_dingtalk(self, config: WebhookConfig, scan_info: Dict) -> Tuple[bool, str]:
        """发送钉钉机器人消息"""
        url = config.webhook_url
        if config.secret:
            timestamp = str(round(time.time() * 1000))
            sign = self._dingtalk_sign(timestamp, config.secret)
            url = f"{url}&timestamp={timestamp}&sign={sign}"

        title = "🔍 网络端口扫描报告"
        text = self._build_dingtalk_text(scan_info)
        
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text
            }
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if data.get('errcode') == 0:
                return True, "钉钉通知发送成功"
            return False, f"钉钉返回错误: {data.get('errmsg', '未知')}"
        except Exception as e:
            return False, str(e)

    def _send_wecom(self, config: WebhookConfig, scan_info: Dict) -> Tuple[bool, str]:
        """发送企业微信机器人消息"""
        text = self._build_wecom_text(scan_info)
        
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": text
            }
        }

        try:
            resp = requests.post(config.webhook_url, json=payload, timeout=10)
            data = resp.json()
            if data.get('errcode') == 0:
                return True, "企业微信通知发送成功"
            return False, f"企业微信返回错误: {data.get('errmsg', '未知')}"
        except Exception as e:
            return False, str(e)

    def _send_feishu(self, config: WebhookConfig, scan_info: Dict) -> Tuple[bool, str]:
        """发送飞书机器人消息"""
        timestamp = str(int(time.time()))
        sign = ""
        if config.secret:
            sign = self._feishu_sign(timestamp, config.secret)

        title = "网络端口扫描报告"
        text = self._build_feishu_text(scan_info)
        
        payload = {
            "timestamp": timestamp,
            "sign": sign,
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"🔍 {title}"},
                    "template": "blue"
                },
                "elements": [
                    {"tag": "markdown", "content": text}
                ]
            }
        }

        try:
            resp = requests.post(config.webhook_url, json=payload, timeout=10)
            data = resp.json()
            if data.get('code') == 0 or data.get('StatusCode') == 0:
                return True, "飞书通知发送成功"
            return False, f"飞书返回错误: {data.get('msg', '未知')}"
        except Exception as e:
            return False, str(e)

    def _build_dingtalk_text(self, info: Dict) -> str:
        """构建钉钉 Markdown 消息"""
        lines = [
            f"## 🔍 网络端口扫描结果",
            f"",
            f"**扫描时间**：{info.get('scan_time', '未知')}",
            f"**扫描耗时**：{info.get('duration', '未知')}",
            f"",
            f"---",
            f"",
            f"**发现主机**：<font color=#FF6B6B>{info.get('total_hosts', 0)} 台</font>",
            f"**开放端口**：<font color=#FF6B6B>{info.get('open_ports', 0)} 个</font>",
        ]
        
        if info.get('high_risk_count', 0) > 0:
            lines.append(f"**高危设备**：<font color=#FF0000>{info['high_risk_count']} 台</font>")
        else:
            lines.append(f"**高危设备**：0 台")
        
        if info.get('report_url'):
            lines.extend(["", f"[📄 查看详细报告]({info['report_url']})"])
        
        lines.extend(["", "---", "此消息由 ScanScript 自动发送"])
        return '\n'.join(lines)

    def _build_wecom_text(self, info: Dict) -> str:
        """构建企业微信 Markdown 消息"""
        lines = [
            f"## 🔍 网络端口扫描结果",
            f"> 扫描时间：<font color=\"comment\">{info.get('scan_time', '未知')}</font>",
            f"> 扫描耗时：<font color=\"comment\">{info.get('duration', '未知')}</font>",
            f"",
            f"**发现主机**：<font color=\"warning\">{info.get('total_hosts', 0)} 台</font>",
            f"**开放端口**：<font color=\"warning\">{info.get('open_ports', 0)} 个</font>",
            f"**高危设备**：<font color=\"warning\">{info.get('high_risk_count', 0)} 台</font>",
        ]
        
        if info.get('report_url'):
            lines.append(f"[查看详细报告]({info['report_url']})")
        
        lines.append("此消息由 ScanScript 自动发送")
        return '\n'.join(lines)

    def _build_feishu_text(self, info: Dict) -> str:
        """构建飞书 Markdown 消息"""
        high_risk = info.get('high_risk_count', 0)
        risk_emoji = "🔴" if high_risk > 0 else "🟢"
        
        lines = [
            f"**扫描时间**：{info.get('scan_time', '未知')}",
            f"**扫描耗时**：{info.get('duration', '未知')}",
            f"",
            f"**发现主机**：**{info.get('total_hosts', 0)}** 台",
            f"**开放端口**：**{info.get('open_ports', 0)}** 个",
            f"**高危设备**：{risk_emoji} **{high_risk}** 台",
        ]
        
        if info.get('report_url'):
            lines.extend(["", f"[📄 查看详细报告]({info['report_url']})"])
        
        lines.extend(["", "---", "此消息由 ScanScript 自动发送"])
        return '\n'.join(lines)

    @staticmethod
    def _dingtalk_sign(timestamp: str, secret: str) -> str:
        """钉钉签名算法"""
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        return quote_plus(base64.b64encode(hmac_code))

    @staticmethod
    def _feishu_sign(timestamp: str, secret: str) -> str:
        """飞书签名算法"""
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(hmac_code).decode('utf-8')


# 全局实例
_webhook_notifier = WebhookNotifier()


def get_webhook_notifier() -> WebhookNotifier:
    """获取全局 Webhook 通知器"""
    return _webhook_notifier
