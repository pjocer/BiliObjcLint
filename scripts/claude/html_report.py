"""
Claude Fixer - HTML 报告生成模块

负责生成交互式 HTML 违规报告
"""
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 添加 scripts 目录到路径以支持绝对导入
_SCRIPT_DIR = Path(__file__).parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from core.lint.logger import get_logger
from claude.utils import escape_html, highlight_objc, read_code_context, read_code_context_by_range

logger = get_logger("claude_fix")


# HTML 报告的 CSS 样式
HTML_STYLES = '''
    :root {
        --bg-color: #ffffff;
        --text-color: #333333;
        --card-bg: #f8f9fa;
        --border-color: #e9ecef;
        --error-bg: #fff5f5;
        --error-border: #fc8181;
        --error-text: #c53030;
        --warning-bg: #fffaf0;
        --warning-border: #f6ad55;
        --warning-text: #c05621;
        --code-bg: #f1f3f5;
    }
    @media (prefers-color-scheme: dark) {
        :root {
            --bg-color: #1a1a2e;
            --text-color: #e0e0e0;
            --card-bg: #16213e;
            --border-color: #0f3460;
            --error-bg: #2d1f1f;
            --error-border: #c53030;
            --error-text: #fc8181;
            --warning-bg: #2d2a1f;
            --warning-border: #c05621;
            --warning-text: #f6ad55;
            --code-bg: #0f3460;
        }
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: var(--bg-color);
        color: var(--text-color);
        line-height: 1.6;
        padding: 20px;
        max-width: 1200px;
        margin: 0 auto;
    }
    h1 {
        font-size: 24px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .summary {
        font-size: 16px;
        color: var(--text-color);
        opacity: 0.8;
        margin-bottom: 30px;
    }
    .error-badge {
        background: var(--error-text);
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 14px;
    }
    .warning-badge {
        background: var(--warning-text);
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 14px;
    }
    .file-section {
        margin-bottom: 24px;
    }
    .file-header {
        font-size: 16px;
        font-weight: 600;
        padding: 12px 16px;
        background: var(--card-bg);
        border: 1px solid var(--border-color);
        border-radius: 8px 8px 0 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .file-path {
        font-family: "SF Mono", Monaco, monospace;
        font-size: 14px;
        word-break: break-all;
    }
    .violations-list {
        border: 1px solid var(--border-color);
        border-top: none;
        border-radius: 0 0 8px 8px;
        overflow: hidden;
    }
    .violation {
        padding: 12px 16px;
        border-bottom: 1px solid var(--border-color);
        display: flex;
        flex-direction: column;
    }
    .violation:last-child {
        border-bottom: none;
        border-radius: 0 0 8px 8px;
    }
    .violation.error {
        background: var(--error-bg);
    }
    .violation.warning {
        background: var(--warning-bg);
    }
    .violation.ignored {
        opacity: 0.5;
    }
    .violation.fixed {
        opacity: 0.6;
        background: rgba(76, 175, 80, 0.1);
    }
    .line-num {
        font-family: "SF Mono", Monaco, monospace;
        font-size: 13px;
        background: var(--code-bg);
        padding: 2px 8px;
        border-radius: 4px;
        white-space: nowrap;
    }
    .severity {
        font-size: 12px;
        font-weight: 600;
        padding: 2px 6px;
        border-radius: 4px;
        text-transform: uppercase;
    }
    .severity.error {
        background: var(--error-border);
        color: white;
    }
    .severity.warning {
        background: var(--warning-border);
        color: white;
    }
    .message {
        flex: 1;
        min-width: 200px;
    }
    .rule {
        font-family: "SF Mono", Monaco, monospace;
        font-size: 12px;
        color: var(--text-color);
        opacity: 0.6;
        background: var(--code-bg);
        padding: 2px 6px;
        border-radius: 4px;
    }
    .footer {
        margin-top: 30px;
        text-align: center;
        font-size: 12px;
        opacity: 0.6;
    }
    .action-bar {
        position: sticky;
        top: 0;
        background: var(--bg-color);
        padding: 16px 0;
        margin-bottom: 20px;
        border-bottom: 1px solid var(--border-color);
        display: flex;
        justify-content: center;
        gap: 16px;
        z-index: 100;
    }
    .btn {
        padding: 12px 32px;
        font-size: 16px;
        font-weight: 600;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.2s;
    }
    .btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .btn:active {
        transform: translateY(0);
    }
    .btn-cancel {
        background: var(--card-bg);
        color: var(--text-color);
        border: 1px solid var(--border-color);
    }
    .btn-fix {
        background: #4CAF50;
        color: white;
    }
    .btn-fix:hover {
        background: #43A047;
    }
    .btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
        transform: none;
    }
    .notice-box {
        background: linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%);
        border: 1px solid #ffc107;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 24px;
        display: flex;
        align-items: flex-start;
        gap: 12px;
        box-shadow: 0 2px 8px rgba(255, 193, 7, 0.15);
    }
    .notice-box .icon {
        font-size: 24px;
        flex-shrink: 0;
        margin-top: 2px;
    }
    .notice-box .content {
        flex: 1;
    }
    .notice-box .title {
        font-weight: 600;
        font-size: 15px;
        color: #8d6e00;
        margin-bottom: 6px;
    }
    .notice-box .desc {
        font-size: 13px;
        color: #6d5600;
        line-height: 1.5;
    }
    @media (prefers-color-scheme: dark) {
        .notice-box {
            background: linear-gradient(135deg, #3d3200 0%, #2d2500 100%);
            border-color: #b38f00;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        }
        .notice-box .title {
            color: #ffd54f;
        }
        .notice-box .desc {
            color: #ffcc80;
        }
    }
    /* 可点击的违规项 */
    .violation-header {
        cursor: pointer;
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
        width: 100%;
    }
    .violation-header:hover {
        opacity: 0.9;
    }
    .expand-icon {
        transition: transform 0.2s;
        font-size: 12px;
        opacity: 0.6;
    }
    .violation.expanded .expand-icon {
        transform: rotate(90deg);
    }
    /* 代码预览区域 */
    .code-preview {
        display: none;
        margin-top: 12px;
        border-radius: 8px;
        overflow: hidden;
        background: #1e1e1e;
        width: 100%;
        box-sizing: border-box;
    }
    .violation.expanded .code-preview {
        display: block;
    }
    .code-actions {
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        padding: 10px 12px;
        background: #2d2d2d;
        border-bottom: 1px solid #404040;
    }
    /* 操作按钮通用样式 */
    .btn-action {
        padding: 6px 14px;
        font-size: 13px;
        font-weight: 500;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.2s;
    }
    .btn-action:disabled {
        cursor: not-allowed;
        opacity: 0.7;
    }
    /* 忽略按钮 */
    .btn-ignore {
        background: #78909C;
        color: white;
    }
    .btn-ignore:hover:not(:disabled) {
        background: #607D8B;
    }
    .btn-ignore[data-state="ignored"] {
        background: #B0BEC5;
        cursor: default;
    }
    /* 修复按钮 */
    .btn-fix-single {
        background: #4CAF50;
        color: white;
    }
    .btn-fix-single:hover:not(:disabled) {
        background: #43A047;
    }
    .btn-fix-single[data-state="fixing"] {
        background: #FFA726;
        cursor: wait;
    }
    .btn-fix-single[data-state="fixed"] {
        background: #66BB6A;
        cursor: default;
    }
    .btn-fix-single[data-state="failed"] {
        background: #EF5350;
    }
    /* Xcode 按钮 */
    .btn-xcode {
        padding: 6px 14px;
        font-size: 13px;
        font-weight: 500;
        background: #007AFF;
        color: white;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 6px;
        transition: background 0.2s;
    }
    .btn-xcode:hover {
        background: #0056CC;
    }
    /* 底部完成按钮 */
    .footer-actions {
        position: sticky;
        bottom: 0;
        background: var(--bg-color);
        padding: 20px;
        border-top: 1px solid var(--border-color);
        text-align: center;
        margin-top: 30px;
    }
    .btn-done, .btn-download, .btn-fix-all {
        padding: 14px 40px;
        font-size: 16px;
        font-weight: 600;
        color: white;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.2s;
        margin: 0 8px;
    }
    .btn-done {
        background: #4CAF50;
    }
    .btn-done:hover {
        background: #43A047;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .btn-download {
        background: #2196F3;
    }
    .btn-download:hover {
        background: #1976D2;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .btn-fix-all {
        background: #FF9800;
    }
    .btn-fix-all:hover {
        background: #F57C00;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .btn-fix-all[data-state="fixing"] {
        background: #FFA726;
        cursor: wait;
    }
    .btn-fix-all[data-state="completed"] {
        background: #66BB6A;
    }
    .btn-fix-all[data-state="failed"] {
        background: #EF5350;
    }
    .btn-done:disabled, .btn-download:disabled, .btn-fix-all:disabled {
        opacity: 0.6;
        cursor: not-allowed;
        transform: none;
    }
    .code-block {
        padding: 12px 0;
        overflow-x: auto;
        font-family: "SF Mono", Monaco, Menlo, monospace;
        font-size: 13px;
        line-height: 1.5;
    }
    .code-line {
        display: flex;
        padding: 2px 12px;
    }
    .code-line.highlighted {
        background: rgba(255, 200, 0, 0.2);
    }
    .code-line-num {
        min-width: 45px;
        padding-right: 12px;
        text-align: right;
        color: #858585;
        user-select: none;
        border-right: 1px solid #404040;
        margin-right: 12px;
    }
    .code-line-content {
        white-space: pre;
        color: #d4d4d4;
    }
    /* ObjC 语法高亮 */
    .hl-keyword { color: #569cd6; }
    .hl-at-keyword { color: #c586c0; }
    .hl-prop { color: #4ec9b0; }
    .hl-string { color: #ce9178; }
    .hl-number { color: #b5cea8; }
    .hl-comment { color: #6a9955; font-style: italic; }
    .hl-preprocessor { color: #c586c0; }
    @media (prefers-color-scheme: light) {
        .code-preview {
            background: #f5f5f5;
        }
        .code-actions {
            background: #e8e8e8;
            border-bottom-color: #d0d0d0;
        }
        .code-line.highlighted {
            background: rgba(255, 200, 0, 0.3);
        }
        .code-line-num {
            color: #6e6e6e;
            border-right-color: #d0d0d0;
        }
        .code-line-content {
            color: #1e1e1e;
        }
        .hl-keyword { color: #0000ff; }
        .hl-at-keyword { color: #af00db; }
        .hl-prop { color: #267f99; }
        .hl-string { color: #a31515; }
        .hl-number { color: #098658; }
        .hl-comment { color: #008000; }
        .hl-preprocessor { color: #af00db; }
    }
'''


def _generate_javascript(port: int) -> str:
    """生成报告页面的 JavaScript 代码"""
    return f'''
        const SERVER_PORT = {port};
        let actionSent = false;

        // 展开/折叠违规项
        function toggleViolation(id) {{
            const el = document.getElementById(id);
            if (el) {{
                el.classList.toggle('expanded');
            }}
        }}

        // 在 Xcode 中打开文件
        async function openInXcode(file, line) {{
            try {{
                const response = await fetch(`http://localhost:${{SERVER_PORT}}/open?file=${{encodeURIComponent(file)}}&line=${{line}}`);
                const result = await response.json();
                if (!result.success) {{
                    alert('打开失败: ' + result.message);
                }}
            }} catch (e) {{
                console.error('打开 Xcode 失败:', e);
                alert('打开 Xcode 失败，请重试');
            }}
        }}

        // 忽略单个违规
        async function ignoreViolation(btn, file, line, rule, message, relatedLines) {{
            event.stopPropagation();
            btn.disabled = true;
            btn.textContent = '处理中...';

            try {{
                const response = await fetch(
                    `http://localhost:${{SERVER_PORT}}/ignore?` +
                    `file=${{encodeURIComponent(file)}}&line=${{line}}&rule=${{rule}}&message=${{encodeURIComponent(message)}}&related_lines=${{relatedLines}}`
                );
                const result = await response.json();
                if (result.success) {{
                    btn.textContent = '已忽略';
                    btn.dataset.state = 'ignored';
                    btn.closest('.violation').classList.add('ignored');
                }} else {{
                    btn.textContent = '忽略';
                    btn.disabled = false;
                    alert('忽略失败: ' + result.message);
                }}
            }} catch (e) {{
                btn.textContent = '忽略';
                btn.disabled = false;
                alert('操作失败');
            }}
        }}

        // 修复单个违规
        async function fixSingleViolation(btn, file, line, rule, message) {{
            event.stopPropagation();
            btn.disabled = true;
            btn.textContent = '修复中...';
            btn.dataset.state = 'fixing';

            try {{
                const response = await fetch(
                    `http://localhost:${{SERVER_PORT}}/fix-single?` +
                    `file=${{encodeURIComponent(file)}}&line=${{line}}&` +
                    `rule=${{rule}}&message=${{encodeURIComponent(message)}}`
                );
                const result = await response.json();
                if (result.success && result.task_id) {{
                    // 修复已启动，轮询查询状态
                    pollFixStatus(btn, result.task_id);
                }} else {{
                    btn.textContent = '重试';
                    btn.dataset.state = 'failed';
                    btn.disabled = false;
                }}
            }} catch (e) {{
                btn.textContent = '重试';
                btn.dataset.state = 'failed';
                btn.disabled = false;
            }}
        }}

        // 轮询修复任务状态
        async function pollFixStatus(btn, taskId) {{
            const maxAttempts = 120;  // 最多轮询 120 次（约 2 分钟）
            const pollInterval = 1000;  // 每秒查询一次
            let attempts = 0;

            const poll = async () => {{
                attempts++;
                try {{
                    const response = await fetch(
                        `http://localhost:${{SERVER_PORT}}/fix-status?task_id=${{taskId}}`
                    );
                    const result = await response.json();

                    if (result.status === 'completed') {{
                        btn.textContent = '已修复';
                        btn.dataset.state = 'fixed';
                        btn.closest('.violation').classList.add('fixed');
                        return;
                    }} else if (result.status === 'failed') {{
                        btn.textContent = '修复失败';
                        btn.dataset.state = 'failed';
                        btn.disabled = false;
                        return;
                    }} else if (result.status === 'running') {{
                        // 更新进度显示
                        btn.textContent = `修复中...${{attempts}}s`;
                        if (attempts < maxAttempts) {{
                            setTimeout(poll, pollInterval);
                        }} else {{
                            btn.textContent = '超时';
                            btn.dataset.state = 'failed';
                            btn.disabled = false;
                        }}
                    }} else {{
                        // 未知状态
                        btn.textContent = '重试';
                        btn.dataset.state = 'failed';
                        btn.disabled = false;
                    }}
                }} catch (e) {{
                    if (attempts < maxAttempts) {{
                        setTimeout(poll, pollInterval);
                    }} else {{
                        btn.textContent = '重试';
                        btn.dataset.state = 'failed';
                        btn.disabled = false;
                    }}
                }}
            }};

            // 启动轮询
            setTimeout(poll, pollInterval);
        }}

        // 下载报告
        function downloadReport() {{
            // 克隆整个文档
            const doc = document.documentElement.cloneNode(true);

            // 移除所有操作按钮区域
            doc.querySelectorAll('.code-actions').forEach(el => el.remove());

            // 移除底部操作按钮
            doc.querySelectorAll('.footer-actions').forEach(el => el.remove());

            // 移除提示框
            doc.querySelectorAll('.notice-box').forEach(el => el.remove());

            // 移除所有 script 标签
            doc.querySelectorAll('script').forEach(el => el.remove());

            // 移除 onclick 属性（展开功能也禁用）
            doc.querySelectorAll('[onclick]').forEach(el => {{
                el.removeAttribute('onclick');
            }});

            // 默认展开所有代码预览
            doc.querySelectorAll('.violation').forEach(el => {{
                el.classList.add('expanded');
            }});

            // 移除展开图标
            doc.querySelectorAll('.expand-icon').forEach(el => el.remove());

            // 移除 violation-header 的 cursor pointer 样式
            const style = doc.querySelector('style');
            if (style) {{
                style.textContent += `
                    .violation-header {{ cursor: default !important; }}
                    .code-preview {{ display: block !important; }}
                `;
            }}

            // 生成文件名（包含日期时间）
            const now = new Date();
            const dateStr = now.toISOString().slice(0, 19).replace(/[T:]/g, '-');
            const filename = `BiliObjCLint_Report_${{dateStr}}.html`;

            // 创建完整的 HTML 文档
            const htmlContent = '<!DOCTYPE html>\\n<html>' + doc.innerHTML + '</html>';

            // 创建 Blob 并下载
            const blob = new Blob([htmlContent], {{ type: 'text/html;charset=utf-8' }});
            const url = URL.createObjectURL(blob);

            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }}

        // 修复所有违规
        async function fixAllViolations() {{
            const btn = document.getElementById('btn-fix-all');
            btn.disabled = true;
            btn.textContent = '修复中...';
            btn.dataset.state = 'fixing';

            try {{
                const response = await fetch(`http://localhost:${{SERVER_PORT}}/fix-all`);
                const result = await response.json();
                if (result.success && result.task_id) {{
                    // 修复已启动，轮询查询状态
                    pollFixAllStatus(btn, result.task_id, result.total);
                }} else {{
                    btn.textContent = '修复全部';
                    btn.dataset.state = 'failed';
                    btn.disabled = false;
                    alert('启动修复失败: ' + (result.message || '未知错误'));
                }}
            }} catch (e) {{
                btn.textContent = '修复全部';
                btn.dataset.state = 'failed';
                btn.disabled = false;
                alert('操作失败');
            }}
        }}

        // 轮询修复全部任务状态
        async function pollFixAllStatus(btn, taskId, total) {{
            const maxAttempts = 300;  // 最多轮询 300 次（约 5 分钟）
            const pollInterval = 1000;  // 每秒查询一次
            let attempts = 0;

            const poll = async () => {{
                attempts++;
                try {{
                    const response = await fetch(
                        `http://localhost:${{SERVER_PORT}}/fix-status?task_id=${{taskId}}`
                    );
                    const result = await response.json();

                    if (result.status === 'completed') {{
                        btn.textContent = '已全部修复';
                        btn.dataset.state = 'completed';
                        // 标记所有违规项为已修复
                        document.querySelectorAll('.violation').forEach(el => {{
                            el.classList.add('fixed');
                        }});
                        document.querySelectorAll('.btn-fix-single').forEach(el => {{
                            el.textContent = '已修复';
                            el.dataset.state = 'fixed';
                            el.disabled = true;
                        }});
                        return;
                    }} else if (result.status === 'failed') {{
                        btn.textContent = '修复失败';
                        btn.dataset.state = 'failed';
                        btn.disabled = false;
                        alert('修复失败: ' + result.message);
                        return;
                    }} else if (result.status === 'running') {{
                        // 更新进度显示
                        btn.textContent = `修复中...${{attempts}}s`;
                        if (attempts < maxAttempts) {{
                            setTimeout(poll, pollInterval);
                        }} else {{
                            btn.textContent = '超时';
                            btn.dataset.state = 'failed';
                            btn.disabled = false;
                        }}
                    }} else {{
                        // 未知状态
                        btn.textContent = '修复全部';
                        btn.dataset.state = 'failed';
                        btn.disabled = false;
                    }}
                }} catch (e) {{
                    if (attempts < maxAttempts) {{
                        setTimeout(poll, pollInterval);
                    }} else {{
                        btn.textContent = '修复全部';
                        btn.dataset.state = 'failed';
                        btn.disabled = false;
                    }}
                }}
            }};

            // 启动轮询
            setTimeout(poll, pollInterval);
        }}

        // 完成并继续编译
        async function finishAndContinue() {{
            if (actionSent) return;
            actionSent = true;

            const btnDone = document.getElementById('btn-done');
            btnDone.disabled = true;
            btnDone.textContent = '正在关闭...';

            try {{
                const response = await fetch(`http://localhost:${{SERVER_PORT}}/done`);
                if (response.ok) {{
                    // 请求成功，尝试关闭页面
                    window.close();
                    // 如果无法关闭，显示提示
                    setTimeout(() => {{
                        document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:-apple-system,sans-serif;"><div style="text-align:center;padding:40px;background:var(--card-bg,#f8f9fa);border-radius:12px;"><h2>✓ 已完成</h2><p style="opacity:0.6;margin-top:10px;">可以关闭此页面</p></div></div>';
                    }}, 100);
                }}
            }} catch (e) {{
                console.error('请求失败:', e);
                alert('操作失败，请重试');
                actionSent = false;
                btnDone.disabled = false;
                btnDone.textContent = '✓ 完成并继续编译';
            }}
        }}
    '''


class HtmlReportGenerator:
    """HTML 报告生成器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def generate(self, violations: List[Dict], port: int = None) -> str:
        """
        生成 HTML 格式的违规报告

        Args:
            violations: 违规列表
            port: 本地服务器端口，如果提供则添加交互按钮

        Returns:
            HTML 文件路径
        """
        # 按文件分组
        by_file = {}
        for v in violations:
            file_path = v.get('file_path') or v.get('file', '')
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(v)

        # 统计
        error_count = sum(1 for v in violations if v.get('severity') == 'error')
        warning_count = len(violations) - error_count

        # 生成 HTML
        html_parts = [f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BiliObjCLint - 代码问题报告</title>
    <style>{HTML_STYLES}</style>
</head>
<body>
    <h1>🔍 BiliObjCLint 代码问题报告</h1>
    <p class="summary">
        发现 <strong>{len(violations)}</strong> 个问题
        ''']

        # 如果提供了端口，添加交互提示
        if port:
            html_parts.append(f'''
    </p>
    <div class="notice-box">
        <span class="icon">⏳</span>
        <div class="content">
            <div class="title">Xcode 正在等待您的操作</div>
            <div class="desc">请阅读下方的代码审查结果，可以对每个问题单独「忽略」或「修复」。处理完成后点击底部的「完成并继续编译」按钮。</div>
        </div>
    </div>
    <p class="summary">
        ''')
        else:
            html_parts.append('')

        if error_count > 0:
            html_parts.append(f'<span class="error-badge">{error_count} errors</span> ')
        if warning_count > 0:
            html_parts.append(f'<span class="warning-badge">{warning_count} warnings</span>')

        html_parts.append('</p>')

        # 按文件输出违规
        for file_path, file_violations in by_file.items():
            # 获取相对路径用于显示
            try:
                display_path = str(Path(file_path).relative_to(self.project_root))
            except ValueError:
                display_path = file_path

            html_parts.append(f'''
    <div class="file-section">
        <div class="file-header">
            <span>📄</span>
            <span class="file-path">{display_path}</span>
        </div>
        <div class="violations-list">''')

            for idx, v in enumerate(sorted(file_violations, key=lambda x: x.get('line', 0))):
                severity = v.get('severity', 'warning')
                line = v.get('line', 0)
                message = v.get('message', '')
                rule = v.get('rule_id') or v.get('rule', '')
                related_lines = v.get('related_lines')  # (start, end) 或 None
                # 格式化为 "start,end" 字符串，供前端传递
                related_lines_str = f"{related_lines[0]},{related_lines[1]}" if related_lines else f"{line},{line}"
                violation_id = f"v-{hash(file_path)}-{idx}"

                # 读取代码上下文（优先使用 related_lines 范围）
                code_lines = read_code_context_by_range(file_path, related_lines, fallback_line=line)

                # 生成代码预览 HTML
                code_html = ''
                if code_lines:
                    code_html = '<div class="code-block">'
                    for ln, content in code_lines:
                        highlighted = 'highlighted' if ln == line else ''
                        highlighted_content = highlight_objc(content)
                        code_html += f'<div class="code-line {highlighted}"><span class="code-line-num">{ln}</span><span class="code-line-content">{highlighted_content}</span></div>'
                    code_html += '</div>'

                # 转义文件路径和消息用于 onclick 属性中的 JS 字符串
                # 需要两层转义：
                #   1. JS 转义：处理 \ 和 '（参数在 JS 单引号字符串中）
                #   2. HTML 属性转义：处理 " & < >（onclick 在双引号 HTML 属性中）
                # HTML 解析器先将 &quot; 还原为 "，再交给 JS 引擎，
                # 此时 " 在单引号 JS 字符串内是合法的
                def _escape_for_onclick(s: str) -> str:
                    # Step 1: JS 转义（单引号字符串上下文）
                    s = s.replace('\\', '\\\\')
                    s = s.replace("'", "\\'")
                    s = s.replace('\n', ' ')
                    s = s.replace('\r', ' ')
                    # Step 2: HTML 属性转义（双引号属性上下文）
                    s = s.replace('&', '&amp;')
                    s = s.replace('"', '&quot;')
                    s = s.replace('<', '&lt;')
                    s = s.replace('>', '&gt;')
                    return s

                escaped_file_path = _escape_for_onclick(file_path)
                escaped_message = _escape_for_onclick(message)

                html_parts.append(f'''
            <div class="violation {severity}" id="{violation_id}" onclick="toggleViolation('{violation_id}')">
                <div class="violation-header">
                    <span class="expand-icon">▶</span>
                    <span class="line-num">Line {line}</span>
                    <span class="severity {severity}">{severity}</span>
                    <span class="message">{escape_html(message)}</span>
                    <span class="rule">{rule}</span>
                </div>
                <div class="code-preview" onclick="event.stopPropagation()">
                    <div class="code-actions">
                        <button class="btn-action btn-ignore" onclick="ignoreViolation(this, '{escaped_file_path}', {line}, '{rule}', '{escaped_message}', '{related_lines_str}')" data-state="normal">
                            忽略
                        </button>
                        <button class="btn-action btn-fix-single" onclick="fixSingleViolation(this, '{escaped_file_path}', {line}, '{rule}', '{escaped_message}')" data-state="normal">
                            修复
                        </button>
                        <button class="btn-xcode" onclick="openInXcode('{escaped_file_path}', {line})">
                            <span>📱</span> 在 Xcode 中打开
                        </button>
                    </div>
                    {code_html}
                </div>
            </div>''')

            html_parts.append('''
        </div>
    </div>''')

        # 添加 JavaScript 和底部按钮（仅当有端口时）
        if port:
            html_parts.append(f'''
    <div class="footer-actions">
        <button class="btn-download" onclick="downloadReport()" id="btn-download">📥 下载报告</button>
        <button class="btn-fix-all" onclick="fixAllViolations()" id="btn-fix-all" data-state="normal">🔧 修复全部</button>
        <button class="btn-done" onclick="finishAndContinue()" id="btn-done">✓ 完成并继续编译</button>
    </div>
    <div class="footer">
        Generated by BiliObjCLint
    </div>
    <script>
        {_generate_javascript(port)}
    </script>
</body>
</html>''')
        else:
            html_parts.append('''
    <div class="footer">
        Generated by BiliObjCLint
    </div>
</body>
</html>''')

        # 写入临时文件
        html_content = ''.join(html_parts)
        report_path = '/tmp/biliobjclint_report.html'
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.debug(f"Generated HTML report: {report_path}")
        return report_path


def open_html_report(report_path: str):
    """
    在浏览器中打开 HTML 报告

    Args:
        report_path: HTML 文件路径
    """
    try:
        subprocess.run(['open', report_path], check=True)
        logger.debug(f"Opened HTML report in browser: {report_path}")
    except Exception as e:
        logger.error(f"Failed to open HTML report: {e}")
