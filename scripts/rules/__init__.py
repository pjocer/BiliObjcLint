# BiliObjCLint Rules Module

from .base_rule import BaseRule
from .naming_rules import (
    ClassPrefixRule,
    PropertyNamingRule,
    ConstantNamingRule,
    MethodNamingRule,
)
from .style_rules import (
    LineLengthRule,
    MethodLengthRule,
    TodoFixmeRule,
    FileHeaderRule,
)
from .memory_rules import (
    WeakDelegateRule,
    BlockRetainCycleRule,
    WrapperEmptyPointerRule,
    DictUsageRule,
    CollectionMutationRule,
)
from .security_rules import (
    ForbiddenApiRule,
    HardcodedCredentialsRule,
    InsecureRandomRule,
)


def get_all_rules():
    """获取所有内置规则类"""
    return [
        # Naming
        ClassPrefixRule,
        PropertyNamingRule,
        ConstantNamingRule,
        MethodNamingRule,
        # Style
        LineLengthRule,
        MethodLengthRule,
        TodoFixmeRule,
        FileHeaderRule,
        # Memory
        WeakDelegateRule,
        BlockRetainCycleRule,
        WrapperEmptyPointerRule,
        DictUsageRule,
        CollectionMutationRule,
        # Security
        ForbiddenApiRule,
        HardcodedCredentialsRule,
        InsecureRandomRule,
    ]


__all__ = [
    'BaseRule',
    'get_all_rules',
    # Naming
    'ClassPrefixRule',
    'PropertyNamingRule',
    'ConstantNamingRule',
    'MethodNamingRule',
    # Style
    'LineLengthRule',
    'MethodLengthRule',
    'TodoFixmeRule',
    'FileHeaderRule',
    # Memory
    'WeakDelegateRule',
    'BlockRetainCycleRule',
    'WrapperEmptyPointerRule',
    'DictUsageRule',
    'CollectionMutationRule',
    # Security
    'ForbiddenApiRule',
    'HardcodedCredentialsRule',
    'InsecureRandomRule',
]
