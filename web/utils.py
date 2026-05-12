"""
Web API 统一响应工具

所有 API 响应必须遵循以下标准格式：
- 成功: { success: true, data: any, message: str }
- 失败: { success: false, message: str, error_code: int, details: dict }
"""
from flask import jsonify


def success_response(data=None, message="成功"):
    """
    统一成功响应格式
    
    Args:
        data: 响应数据
        message: 消息文本
    Returns:
        Flask JSON response
    """
    return jsonify({
        'success': True,
        'message': message,
        'data': data
    })


def error_response(message="失败", code=400, details=None, extra=None):
    """
    统一错误响应格式
    
    Args:
        message: 错误消息
        code: HTTP 状态码
        details: 错误详情
        extra: 额外字段
    Returns:
        (Flask JSON response, HTTP status code)
    """
    resp = {
        'success': False,
        'message': message,
        'error_code': code,
        'details': details or {}
    }
    if extra:
        resp.update(extra)
    return jsonify(resp), code


def paginated_response(items, total, page=1, page_size=20):
    """
    统一分页响应格式
    
    Args:
        items: 数据列表
        total: 总数
        page: 当前页
        page_size: 每页大小
    Returns:
        Flask JSON response
    """
    return success_response({
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total + page_size - 1) // page_size) if page_size > 0 else 0
    })
