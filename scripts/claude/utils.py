"""
Claude Fixer - 工具函数模块

包含代码高亮、HTML转义、代码上下文读取等工具函数
"""
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

# 添加 scripts 目录到路径以支持绝对导入
_SCRIPT_DIR = Path(__file__).parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from core.lint.logger import get_logger

logger = get_logger("claude_fix")


def escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))


def highlight_objc(code: str) -> str:
    """
    简单的 Objective-C 语法高亮

    使用占位符系统保护字符串和注释，避免后续正则匹配到已生成的 HTML 属性

    Args:
        code: 代码文本

    Returns:
        带有 HTML 高亮标记的代码
    """
    # 使用占位符保护字符串和注释
    # 重要：必须在 HTML 转义之前提取，因为转义后 " 变成 &quot; 会破坏正则匹配
    placeholders = []

    def save_and_escape(match, match_type):
        """保存匹配内容并转义 HTML"""
        idx = len(placeholders)
        # 对提取的内容进行 HTML 转义
        escaped_content = escape_html(match.group(0))
        placeholders.append((match_type, escaped_content))
        return f'\x00{match_type}_{idx}\x00'

    # 1. 先提取注释（优先级最高，避免字符串匹配到注释内容）
    code = re.sub(r'//.*?$', lambda m: save_and_escape(m, 'COMMENT'), code)

    # 2. 提取字符串（在 HTML 转义之前，使用原始引号匹配）
    code = re.sub(r'@"[^"]*"', lambda m: save_and_escape(m, 'STRING'), code)  # ObjC 字符串 @"..."
    code = re.sub(r'"(?:[^"\\]|\\.)*"', lambda m: save_and_escape(m, 'STRING'), code)  # C 字符串 "..."

    # 3. 现在对剩余代码进行 HTML 转义
    code = escape_html(code)

    # 4. 处理关键字等，不会匹配到字符串和注释（它们已被占位符替代）
    # 关键字
    keywords = r'\b(if|else|for|while|do|switch|case|default|break|continue|return|goto|typedef|struct|enum|union|sizeof|static|extern|const|volatile|inline|register|auto|signed|unsigned|void|char|short|int|long|float|double|bool|BOOL|YES|NO|nil|NULL|self|super|id|Class|SEL|IMP|instancetype|NS_ASSUME_NONNULL_BEGIN|NS_ASSUME_NONNULL_END)\b'
    code = re.sub(keywords, r'<span class="hl-keyword">\1</span>', code)

    # @关键字
    at_keywords = r'(@interface|@implementation|@end|@protocol|@property|@synthesize|@dynamic|@class|@public|@private|@protected|@package|@selector|@encode|@try|@catch|@finally|@throw|@synchronized|@autoreleasepool|@optional|@required|@import|@available)'
    code = re.sub(at_keywords, r'<span class="hl-at-keyword">\1</span>', code)

    # 属性关键字
    prop_keywords = r'\b(nonatomic|atomic|strong|weak|copy|assign|retain|readonly|readwrite|getter|setter|nullable|nonnull)\b'
    code = re.sub(prop_keywords, r'<span class="hl-prop">\1</span>', code)

    # 数字
    code = re.sub(r'\b(\d+\.?\d*[fFlL]?)\b', r'<span class="hl-number">\1</span>', code)

    # 预处理指令
    code = re.sub(r'^(\s*)(#\w+)', r'\1<span class="hl-preprocessor">\2</span>', code)

    # 5. 恢复字符串和注释，并添加高亮
    for i, (match_type, escaped_content) in enumerate(placeholders):
        placeholder = f'\x00{match_type}_{i}\x00'
        if match_type == 'COMMENT':
            code = code.replace(placeholder, f'<span class="hl-comment">{escaped_content}</span>')
        elif match_type == 'STRING':
            code = code.replace(placeholder, f'<span class="hl-string">{escaped_content}</span>')

    return code


def read_code_context(file_path: str, line: int, context_lines: int = 3) -> List[Tuple[int, str]]:
    """
    读取代码上下文

    Args:
        file_path: 文件路径
        line: 目标行号
        context_lines: 上下文行数

    Returns:
        [(line_number, code_line), ...]
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()

        start = max(0, line - context_lines - 1)
        end = min(len(all_lines), line + context_lines)

        result = []
        for i in range(start, end):
            result.append((i + 1, all_lines[i].rstrip('\n\r')))
        return result
    except Exception as e:
        logger.warning(f"Failed to read code context from {file_path}: {e}")
        return []


def cleanup_temp_files(*paths):
    """
    清理临时文件

    Args:
        paths: 要删除的文件路径列表
    """
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
                logger.debug(f"Cleaned up temp file: {path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {path}: {e}")
