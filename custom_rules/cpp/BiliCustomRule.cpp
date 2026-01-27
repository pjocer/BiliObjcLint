/**
 * 示例 C++ 自定义规则
 *
 * 这个文件展示如何为 OCLint 编写 C++ 自定义规则。
 * C++ 规则可以进行 AST 级别的深度分析。
 *
 * 编译步骤:
 * 1. 确保已编译 OCLint（运行 scripts/build_oclint.sh）
 * 2. 将此文件添加到 oclint/oclint-rules/rules/custom/
 * 3. 重新编译 OCLint
 *
 * 规则开发参考:
 * - OCLint 规则开发指南: http://docs.oclint.org/en/stable/rules/custom.html
 * - Clang AST 参考: https://clang.llvm.org/doxygen/
 */

#include "oclint/AbstractASTVisitorRule.h"
#include "oclint/RuleSet.h"

using namespace std;
using namespace clang;
using namespace oclint;

/**
 * 示例规则：禁止使用 @synchronized
 *
 * @synchronized 可能导致性能问题，建议使用更轻量的锁机制
 */
class NoSynchronizedRule : public AbstractASTVisitorRule<NoSynchronizedRule>
{
public:
    virtual const string name() const override
    {
        return "bili no synchronized";
    }

    virtual int priority() const override
    {
        return 2;  // 1 = error, 2 = warning, 3 = note
    }

    virtual const string category() const override
    {
        return "bili";
    }

    virtual const string description() const override
    {
        return "Avoid using @synchronized, consider using dispatch_semaphore or os_unfair_lock instead.";
    }

    bool VisitObjCAtSynchronizedStmt(ObjCAtSynchronizedStmt *node)
    {
        addViolation(node, this, "@synchronized 可能影响性能，建议使用 dispatch_semaphore 或 os_unfair_lock");
        return true;
    }
};

/**
 * 示例规则：方法返回值检查
 *
 * 检测 alloc/init 分离调用（可能导致内存泄漏）
 */
class AllocInitSeparationRule : public AbstractASTVisitorRule<AllocInitSeparationRule>
{
public:
    virtual const string name() const override
    {
        return "bili alloc init separation";
    }

    virtual int priority() const override
    {
        return 1;  // error 级别
    }

    virtual const string category() const override
    {
        return "bili";
    }

    virtual const string description() const override
    {
        return "[[Class alloc] init] should be called together, not separately.";
    }

    bool VisitObjCMessageExpr(ObjCMessageExpr *expr)
    {
        // 检测 [obj alloc] 调用
        if (expr->getSelector().getAsString() == "alloc")
        {
            // 检查父节点是否直接是 init 调用
            // 如果不是，报告违规
            // ... 实现细节
        }

        return true;
    }
};

// 注册规则
static RuleSet rules(new NoSynchronizedRule());
// static RuleSet rules2(new AllocInitSeparationRule());

/**
 * 更多自定义规则模板:
 *
 * class YourRule : public AbstractASTVisitorRule<YourRule>
 * {
 * public:
 *     virtual const string name() const override { return "your rule name"; }
 *     virtual int priority() const override { return 2; }
 *     virtual const string category() const override { return "bili"; }
 *     virtual const string description() const override { return "..."; }
 *
 *     // 访问各种 AST 节点
 *     bool VisitObjCMethodDecl(ObjCMethodDecl *decl) { ... }
 *     bool VisitObjCPropertyDecl(ObjCPropertyDecl *decl) { ... }
 *     bool VisitIfStmt(IfStmt *stmt) { ... }
 *     bool VisitForStmt(ForStmt *stmt) { ... }
 *     bool VisitCallExpr(CallExpr *expr) { ... }
 * };
 */
