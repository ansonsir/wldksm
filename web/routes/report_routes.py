"""
报告、模板、邮件发送相关路由
/api/reports, /api/templates, /api/reports/send
"""
from pathlib import Path
from datetime import datetime
import logging
from flask import Blueprint, request, jsonify, send_file, current_app
from web.middleware.auth_middleware import require_auth, require_csrf
from core.template_manager import TemplateManager

logger = logging.getLogger(__name__)

report_bp = Blueprint('report', __name__, url_prefix='/api/v1')


def _get_services():
    """获取全局服务实例"""
    return (
        current_app.config['db_manager'],
        current_app.config['mailer'],
    )


def _get_project_root():
    return current_app.config['project_root']


# ==================== 报告管理 ====================

@report_bp.route('/reports', methods=['GET'])
@require_auth
def get_reports():
    """获取报告列表"""
    try:
        db_manager, _ = _get_services()
        project_root = _get_project_root()

        report_dirs = [
            project_root / "data" / "reports",
            project_root / "archive" / "reports",
        ]
        for d in report_dirs:
            d.mkdir(parents=True, exist_ok=True)

        seen_paths = set()
        all_reports = []

        records = db_manager.get_scan_records(limit=200)
        for r in records:
            if not r.report_file:
                continue
            report_path = Path(r.report_file)
            if not report_path.is_absolute():
                report_path = project_root / report_path
            if not report_path.exists():
                continue
            path_str = str(report_path)
            seen_paths.add(path_str)
            area = db_manager.get_scan_area_by_id(r.area_id)
            stat = report_path.stat()
            all_reports.append({
                'id': r.id,
                'name': report_path.name,
                'path': path_str,
                'size': stat.st_size,
                'created': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'record_id': r.id,
                'area': area.area_name if area else '-',
                'status': r.scan_status,
            })

        for report_dir in report_dirs:
            for file_path in sorted(report_dir.glob("*.docx"), reverse=True):
                path_str = str(file_path)
                if path_str in seen_paths:
                    continue
                seen_paths.add(path_str)
                stat = file_path.stat()
                all_reports.append({
                    'id': file_path.stem,
                    'name': file_path.name,
                    'path': path_str,
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'record_id': None,
                    'area': '-',
                    'status': 'unknown',
                })

        all_reports.sort(key=lambda x: x['created'] or '', reverse=True)
        return jsonify({'success': True, 'data': all_reports})
    except Exception as e:
        logger.error("获取报告列表失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '获取报告列表失败，请稍后重试'}), 500


@report_bp.route('/reports/download', methods=['POST'])
@require_auth
@require_csrf
def download_report():
    """下载报告文件"""
    try:
        project_root = _get_project_root()
        data = request.get_json() or {}
        file_path = data.get('path')
        if not file_path:
            return jsonify({'success': False, 'message': '缺少文件路径'}), 400

        path = Path(file_path)
        if not path.is_absolute():
            path = project_root / path

        if not path.exists():
            alt_path = project_root / file_path
            if alt_path.exists():
                path = alt_path
            else:
                return jsonify({'success': False, 'message': '文件不存在'}), 404

        # 路径穿越防护：确保文件在项目目录下
        try:
            path.resolve().relative_to(project_root.resolve())
        except ValueError:
            return jsonify({'success': False, 'message': '非法的文件路径'}), 403

        return send_file(str(path), as_attachment=True, download_name=path.name)
    except Exception as e:
        logger.error("下载报告失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '下载报告失败，请稍后重试'}), 500


@report_bp.route('/reports/delete', methods=['POST'])
@require_auth
@require_csrf
def delete_reports():
    """删除报告文件"""
    try:
        project_root = _get_project_root()
        data = request.get_json() or {}
        paths = data.get('paths', [])
        if not paths:
            return jsonify({'success': False, 'message': '未选择要删除的报告'}), 400

        deleted = []
        failed = []
        for file_path in paths:
            path = Path(file_path)
            if not path.is_absolute():
                path = project_root / path

            try:
                path.resolve().relative_to(project_root.resolve())
            except ValueError:
                failed.append({'path': file_path, 'reason': '路径不在项目目录下'})
                continue

            if path.exists() and path.is_file():
                try:
                    path.unlink()
                    deleted.append(file_path)
                except Exception as e:
                    failed.append({'path': file_path, 'reason': str(e)})
            else:
                failed.append({'path': file_path, 'reason': '文件不存在'})

        msg = f'成功删除 {len(deleted)} 个文件'
        if failed:
            msg += f'，{len(failed)} 个失败'

        return jsonify({
            'success': len(deleted) > 0 or len(paths) == 0,
            'message': msg,
            'deleted': deleted,
            'failed': failed
        })
    except Exception as e:
        logger.error("删除报告失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '删除报告失败，请稍后重试'}), 500


@report_bp.route('/reports/send', methods=['POST'])
@require_auth
@require_csrf
def send_report_mail():
    """发送报告邮件"""
    try:
        _, mailer = _get_services()
        data = request.get_json()
        report_path = data.get('report_path')
        recipients_str = data.get('recipients', '')
        subject = data.get('subject', '')
        body = data.get('body', '')

        if not report_path:
            return jsonify({'success': False, 'message': '缺少报告文件路径'}), 400

        recipients = [r.strip() for r in recipients_str.split(',') if r.strip()]
        if not recipients:
            return jsonify({'success': False, 'message': '收件人列表为空'}), 400

        success, message = mailer.send_report(
            report_path=report_path,
            recipients=recipients,
            subject=subject,
            body=body,
        )
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        logger.error("发送报告邮件失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '发送报告邮件失败，请稍后重试'}), 500


# ==================== 模板管理 ====================

@report_bp.route('/templates', methods=['GET'])
@require_auth
def get_templates():
    """获取模板列表"""
    try:
        db_manager, _ = _get_services()
        template_manager = TemplateManager(db_manager=db_manager)
        templates = template_manager.list_templates()
        return jsonify({'success': True, 'data': templates})
    except Exception as e:
        logger.error("获取模板列表失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '获取模板列表失败，请稍后重试'}), 500


@report_bp.route('/templates/upload', methods=['POST'])
@require_auth
@require_csrf
def upload_template():
    """上传模板文件"""
    try:
        project_root = _get_project_root()
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '文件名为空'}), 400

        # 1. 检查扩展名
        if not file.filename.lower().endswith('.docx'):
            return jsonify({'success': False, 'message': '只支持 .docx 文件'}), 400

        # 2. 验证文件头（ZIP魔术字节）
        file_content = file.read(8)
        file.seek(0)
        if file_content[:4] != b'PK\x03\x04':
            return jsonify({'success': False, 'message': '文件不是有效的 DOCX 格式'}), 400

        # 3. 安全文件名（防止路径穿越）
        import uuid, re
        safe_name = Path(file.filename).name
        safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', safe_name)
        if safe_name != Path(file.filename).name:
            safe_name = f"{uuid.uuid4().hex}_{safe_name}"

        template_dir = project_root / "data" / "templates"
        template_dir.mkdir(parents=True, exist_ok=True)

        # 4. 确保保存路径在 template_dir 下
        save_path = (template_dir / safe_name).resolve()
        try:
            save_path.relative_to(template_dir.resolve())
        except ValueError:
            return jsonify({'success': False, 'message': '非法的文件路径'}), 403

        file.save(str(save_path))

        db_manager, _ = _get_services()
        template_manager = TemplateManager(str(template_dir), db_manager)
        success, msg = template_manager.add_template(str(save_path), save_path.stem)

        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        logger.error("上传模板失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '上传模板失败，请稍后重试'}), 500


@report_bp.route('/templates/delete', methods=['POST'])
@require_auth
@require_csrf
def delete_template():
    """删除模板"""
    try:
        db_manager, _ = _get_services()
        project_root = _get_project_root()
        data = request.get_json() or {}
        template_id = data.get('id')
        file_path = data.get('path')

        if not file_path:
            return jsonify({'success': False, 'message': '缺少文件路径'}), 400

        path = Path(file_path)
        if not path.is_absolute():
            path = project_root / path
        # 路径穿越保护
        resolved_path = path.resolve()
        project_root_resolved = project_root.resolve()
        if not str(resolved_path).startswith(str(project_root_resolved)):
            return jsonify({'success': False, 'message': '非法文件路径'}), 403
        if resolved_path.exists() and resolved_path.is_file():
            resolved_path.unlink()

        if template_id:
            db_manager.delete_template(template_id)

        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        logger.error("删除模板失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '删除模板失败，请稍后重试'}), 500


@report_bp.route('/templates/preview', methods=['POST'])
@require_auth
@require_csrf
def preview_template():
    """预览模板内容"""
    try:
        project_root = _get_project_root()
        data = request.get_json() or {}
        file_path = data.get('path')
        if not file_path:
            return jsonify({'success': False, 'message': '缺少文件路径'}), 400

        path = Path(file_path)
        if not path.is_absolute():
            path = project_root / path

        # 路径穿越保护
        resolved_path = path.resolve()
        project_root_resolved = project_root.resolve()
        if not str(resolved_path).startswith(str(project_root_resolved)):
            return jsonify({'success': False, 'message': '非法文件路径'}), 403

        if not resolved_path.exists():
            return jsonify({'success': False, 'message': '文件不存在'}), 404

        from docx import Document
        doc = Document(str(resolved_path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

        return jsonify({
            'success': True,
            'data': {
                'name': path.name,
                'paragraphs': paragraphs[:100],
                'total': len(paragraphs)
            }
        })
    except Exception as e:
        logger.error("预览模板失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '预览模板失败，请稍后重试'}), 500
