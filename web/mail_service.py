"""
邮件发送服务模块
支持SMTP配置管理和报告邮件发送
SMTP密码使用Fernet加密存储，防止明文泄露
"""
import smtplib
import logging
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from cryptography.fernet import Fernet

from core.database import DatabaseManager, EmailSettings

# SMTP密码加密密钥文件路径
_FERNET_KEY_FILE = Path(__file__).parent.parent / "data" / ".smtp_fernet_key"


def _get_fernet() -> Fernet:
    """获取或生成Fernet加密实例"""
    if _FERNET_KEY_FILE.exists():
        key = _FERNET_KEY_FILE.read_bytes()
    else:
        key = Fernet.generate_key()
        _FERNET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _FERNET_KEY_FILE.write_bytes(key)
        import os
        os.chmod(str(_FERNET_KEY_FILE), 0o600)
    return Fernet(key)


def _encrypt_password(password: str) -> str:
    """加密SMTP密码"""
    if not password:
        return ""
    try:
        f = _get_fernet()
        return f.encrypt(password.encode('utf-8')).decode('utf-8')
    except Exception:
        return password  # 加密失败时返回原密码（降级处理）


def _decrypt_password(encrypted: str) -> str:
    """解密SMTP密码"""
    if not encrypted:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(encrypted.encode('utf-8')).decode('utf-8')
    except Exception:
        return encrypted  # 解密失败时返回原值（兼容旧数据）


@dataclass
class MailConfig:
    """邮件配置"""
    smtp_server: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_ssl: bool = True
    skip_login: bool = False  # 跳过登录（用于IP白名单认证的服务器）
    default_sender: str = ""
    default_recipients: str = ""

    def is_configured(self) -> bool:
        return bool(self.smtp_server)


class ReportMailer:
    """报告邮件发送器"""

    def __init__(self, config: Optional[MailConfig] = None,
                 db_manager: Optional[DatabaseManager] = None,
                 logger: Optional[logging.Logger] = None):
        self.config = config
        self.db = db_manager
        self.logger = logger or logging.getLogger("ReportMailer")

        if not self.config and self.db:
            self._load_from_db()

    def _load_from_db(self):
        """从数据库加载邮件配置"""
        if not self.db:
            return
        settings = self.db.get_email_settings()
        if settings:
            self.config = MailConfig(
                smtp_server=settings.smtp_server,
                smtp_port=settings.smtp_port,
                smtp_user=settings.smtp_user,
                smtp_password=_decrypt_password(settings.smtp_password),
                smtp_ssl=settings.smtp_ssl,
                skip_login=settings.skip_login,
                default_sender=settings.default_sender,
                default_recipients=settings.default_recipients,
            )

    def save_to_db(self, config: MailConfig) -> bool:
        """保存邮件配置到数据库（密码加密存储）"""
        if not self.db:
            self.logger.warning("没有数据库连接，无法保存邮件配置")
            return False

        settings = EmailSettings(
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            smtp_password=_encrypt_password(config.smtp_password),
            smtp_ssl=config.smtp_ssl,
            skip_login=config.skip_login,
            default_sender=config.default_sender,
            default_recipients=config.default_recipients,
        )
        return self.db.update_email_settings(settings)

    def test_connection(self, config: Optional[MailConfig] = None) -> Tuple[bool, str]:
        """
        测试SMTP连接

        :param config: 邮件配置（可选，使用当前配置）
        :return: (是否成功, 消息)
        """
        cfg = config or self.config
        if not cfg or not cfg.is_configured():
            return False, "邮件配置不完整"

        try:
            if cfg.smtp_ssl:
                # SSL模式（465端口）
                self.logger.info(f"尝试SSL模式连接: {cfg.smtp_server}:{cfg.smtp_port}")
                server = smtplib.SMTP_SSL(cfg.smtp_server, cfg.smtp_port, timeout=10)
            else:
                # STARTTLS模式（587端口）
                self.logger.info(f"尝试STARTTLS模式连接: {cfg.smtp_server}:{cfg.smtp_port}")
                server = smtplib.SMTP(cfg.smtp_server, cfg.smtp_port, timeout=10)
                server.starttls()

            # 调试信息
            server.set_debuglevel(0)
            
            # 检查是否跳过登录
            if cfg.skip_login:
                self.logger.info("跳过登录（IP白名单认证模式）")
                # 不登录，直接测试连接
                server.quit()
                return True, "SMTP连接测试成功（IP白名单模式）"
            
            # 尝试登录
            server.login(cfg.smtp_user, cfg.smtp_password)
            server.quit()
            return True, "SMTP连接测试成功"

        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP认证失败: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
            
        except smtplib.SMTPNotSupportedError as e:
            # 服务器不支持AUTH，建议开启skip_login
            error_msg = f"服务器不支持SMTP AUTH: {str(e)}\n\n建议：开启'跳过登录'选项（适用于IP白名单认证的服务器）"
            self.logger.error(error_msg)
            return False, error_msg
            
        except smtplib.SMTPException as e:
            # 如果SSL模式失败，尝试使用普通SMTP连接
            if cfg.smtp_ssl:
                self.logger.warning(f"SSL模式失败，尝试普通SMTP连接: {e}")
                try:
                    server = smtplib.SMTP(cfg.smtp_server, cfg.smtp_port, timeout=10)
                    
                    if cfg.skip_login:
                        self.logger.info("跳过登录（IP白名单认证模式）")
                        server.quit()
                        return True, "SMTP连接测试成功（普通模式，IP白名单）"
                    
                    # 不调用starttls()，直接登录
                    server.login(cfg.smtp_user, cfg.smtp_password)
                    server.quit()
                    return True, "SMTP连接测试成功（普通模式）"
                except smtplib.SMTPNotSupportedError as e2:
                    error_msg = f"服务器不支持SMTP AUTH: {str(e2)}\n\n建议：开启'跳过登录'选项"
                    self.logger.error(error_msg)
                    return False, error_msg
                except Exception as e2:
                    error_msg = f"SMTP连接测试失败: {str(e2)}"
                    self.logger.error(error_msg)
                    return False, error_msg
            else:
                error_msg = f"SMTP连接测试失败: {str(e)}"
                self.logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"SMTP连接测试失败: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    def send_report(
        self,
        report_path: str,
        recipients: List[str],
        subject: Optional[str] = None,
        body: Optional[str] = None,
        sender: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        发送报告邮件

        :param report_path: 报告文件路径
        :param recipients: 收件人列表
        :param subject: 邮件主题
        :param body: 邮件正文
        :param sender: 发件人
        :return: (是否成功, 消息)
        """
        if not self.config or not self.config.is_configured():
            return False, "邮件配置不完整，请先配置SMTP"

        if not recipients:
            return False, "收件人列表为空"

        report_path = Path(report_path)
        if not report_path.exists():
            return False, f"报告文件不存在: {report_path}"

        try:
            # 构建邮件
            msg = MIMEMultipart()
            msg['From'] = sender or self.config.default_sender or self.config.smtp_user
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject or f"网络端口扫描报告 - {report_path.name}"

            # 邮件正文
            body_text = body or f"请查收附件中的网络端口扫描报告。\n\n报告文件: {report_path.name}"
            msg.attach(MIMEText(body_text, 'plain', 'utf-8'))

            # 附件
            with open(report_path, 'rb') as f:
                # 根据扩展名确定 MIME 类型
                suffix = report_path.suffix.lower()
                mime_types = {
                    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    '.doc': 'application/msword',
                    '.pdf': 'application/pdf',
                    '.txt': 'text/plain',
                }
                maintype, subtype = 'application', 'octet-stream'
                if suffix in mime_types:
                    parts = mime_types[suffix].split('/')
                    if len(parts) == 2:
                        maintype, subtype = parts

                attachment = MIMEBase(maintype, subtype)
                attachment.set_payload(f.read())
                encoders.encode_base64(attachment)

                # 对中文文件名进行 RFC 5987 编码，确保跨客户端兼容性
                filename = report_path.name
                try:
                    filename.encode('ascii')
                    # 纯 ASCII 文件名，直接引用
                    disposition = f'attachment; filename="{filename}"'
                except UnicodeEncodeError:
                    # 含中文等非 ASCII 字符，使用 RFC 5987 编码
                    from urllib.parse import quote
                    encoded = quote(filename, safe='')
                    disposition = f"attachment; filename*=UTF-8''{encoded}"

                # 先设置 Content-Type 头（含文件名），再设置 Content-Disposition
                attachment.add_header('Content-Type', f'{maintype}/{subtype}; name="{filename}"')
                attachment.add_header('Content-Disposition', disposition)
                msg.attach(attachment)

            # 发送邮件
            try:
                if self.config.smtp_ssl:
                    self.logger.info(f"使用SSL模式发送邮件: {self.config.smtp_server}:{self.config.smtp_port}")
                    server = smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port, timeout=30)
                else:
                    self.logger.info(f"使用STARTTLS模式发送邮件: {self.config.smtp_server}:{self.config.smtp_port}")
                    server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port, timeout=30)
                    server.starttls()

                # 检查是否跳过登录
                if not self.config.skip_login:
                    server.login(self.config.smtp_user, self.config.smtp_password)
                    
                server.send_message(msg)
                server.quit()

                self.logger.info(f"报告邮件已发送至: {', '.join(recipients)}")
                return True, f"邮件发送成功，收件人: {', '.join(recipients)}"
                
            except smtplib.SMTPNotSupportedError as e:
                # 服务器不支持AUTH
                error_msg = f"服务器不支持SMTP AUTH: {str(e)}"
                self.logger.error(error_msg)
                return False, error_msg
                
            except smtplib.SMTPRecipientsRefused as e:
                # 收件人被拒绝（服务器策略限制）
                error_msg = f"收件人被服务器拒绝: {str(e)}\n\n可能原因：\n1. 服务器不允许发送到该邮箱\n2. 发件人未被授权\n3. 需要联系IT部门添加白名单"
                self.logger.error(error_msg)
                return False, error_msg
                
            except smtplib.SMTPException as e:
                # 如果SSL模式失败且没有开启skip_login，尝试普通SMTP
                if self.config.smtp_ssl and not self.config.skip_login:
                    self.logger.warning(f"SSL模式发送失败，尝试普通SMTP: {e}")
                    try:
                        server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port, timeout=30)
                        server.login(self.config.smtp_user, self.config.smtp_password)
                        server.send_message(msg)
                        server.quit()
                        
                        self.logger.info(f"报告邮件已发送至: {', '.join(recipients)}")
                        return True, f"邮件发送成功（普通模式），收件人: {', '.join(recipients)}"
                    except Exception as e2:
                        self.logger.error(f"普通SMTP发送也失败: {e2}")
                        return False, f"发送邮件失败: {str(e2)}"
                else:
                    # skip_login=True时，不降级重试，直接返回错误
                    error_msg = f"SMTP发送失败: {str(e)}"
                    self.logger.error(error_msg)
                    return False, error_msg

        except Exception as e:
            self.logger.error(f"发送邮件失败: {e}")
            return False, f"发送邮件失败: {str(e)}"


