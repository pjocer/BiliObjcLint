//
//  test_block_retain.m
//  BiliObjCLint Test Cases
//
//  Block Retain Cycle Rule Test Cases
//

#import <Foundation/Foundation.h>

@interface TestBlockRetainCycle : NSObject
@property (nonatomic, copy) void (^completionBlock)(void);
- (void)doSomethingWithBlock:(void(^)(void))block;
- (void)doBlock:(void(^)(void))block;
- (void)doAnotherBlock:(void(^)(void))block;
- (void)doWork;
- (void)innerWork;
- (void)performSelector;
- (void)updateUI;
- (void)handleNotification:(NSNotification *)note;
@end

@implementation TestBlockRetainCycle

// ===========================================
// 1. 无 weak 转换 → ERROR
// ===========================================

- (void)testCase1_1_SimpleRetainCycle {
    // 1.1 最简单的循环引用
    [self doSomethingWithBlock:^{
        [self doWork];  // ERROR: Block 内直接使用 self 可能导致循环引用
    }];
}

- (void)testCase1_2_SelfVariousUsage {
    // 1.2 self 的各种使用方式
    [self doSomethingWithBlock:^{
        self.completionBlock = nil;  // ERROR
        [self performSelector];       // ERROR
    }];
}

- (void)testCase1_3_NestedBlock {
    // 1.3 嵌套 block
    [self doSomethingWithBlock:^{
        [self doAnotherBlock:^{
            [self innerWork];  // ERROR
        }];
    }];
}

// ===========================================
// 2. Manual Weak，无 Strong
// ===========================================

- (void)testCase2_1_WeakButUseSelf {
    // 2.1 有 weak 但使用了 self → ERROR
    __weak typeof(self) wSelf = self;
    [self doSomethingWithBlock:^{
        [self doWork];  // ERROR: 已声明 wSelf，应使用 wSelf 而不是 self
    }];
}

- (void)testCase2_2_WeakUseWeakSelf {
    // 2.2 有 weak 使用 weakSelf → WARNING
    __weak typeof(self) wSelf = self;
    [self doSomethingWithBlock:^{
        [wSelf doWork];  // WARNING: 建议转为 strongSelf 防止执行过程中变为 nil
    }];
}

- (void)testCase2_3_VariousNamingStyles {
    // 2.3 各种命名风格
    __weak typeof(self) weSelf = self;
    [self doBlock:^{
        [weSelf doWork];  // WARNING
    }];
}

- (void)testCase2_4_TypeofVariants {
    // 2.4 不同 typeof 写法
    __weak __typeof(self) weakSelf = self;
    [self doBlock:^{
        [weakSelf doWork];  // WARNING
    }];
}

- (void)testCase2_5_TypeofWithDoubleUnderscore {
    __weak __typeof__(self) ws = self;
    [self doBlock:^{
        [ws doWork];  // WARNING
    }];
}

// ===========================================
// 3. Manual Weak + Strong
// ===========================================

- (void)testCase3_1_WeakStrongCorrect {
    // 3.1 有 weak+strong，使用 strongSelf → OK
    __weak typeof(self) wSelf = self;
    [self doSomethingWithBlock:^{
        __strong typeof(wSelf) sSelf = wSelf;
        if (!sSelf) return;
        [sSelf doWork];  // OK: 正确用法
    }];
}

- (void)testCase3_2_WeakStrongButUseSelf {
    // 3.2 有 weak+strong，但使用了 self → ERROR
    __weak typeof(self) wSelf = self;
    [self doSomethingWithBlock:^{
        __strong typeof(wSelf) sSelf = wSelf;
        [self doWork];  // ERROR: 已声明 sSelf，应使用 sSelf 而不是 self
    }];
}

- (void)testCase3_3_WeakStrongButUseWeakSelf {
    // 3.3 有 weak+strong，但使用了 weakSelf → WARNING
    __weak typeof(self) wSelf = self;
    [self doSomethingWithBlock:^{
        __strong typeof(wSelf) sSelf = wSelf;
        [wSelf doWork];  // WARNING: 已声明 sSelf，建议使用 sSelf 而不是 wSelf
    }];
}

- (void)testCase3_4_StrongSelfNaming {
    // 3.4 各种 strong 命名风格
    __weak typeof(self) weakSelf = self;
    [self doBlock:^{
        __strong typeof(weakSelf) strongSelf = weakSelf;
        [strongSelf doWork];  // OK
    }];
}

// ===========================================
// 4. @weakify 宏方式
// ===========================================

- (void)testCase4_1_WeakifyStrongifyCorrect {
    // 4.1 @weakify + @strongify → OK
    @weakify(self);
    [self doSomethingWithBlock:^{
        @strongify(self);
        [self doWork];  // OK: @strongify 已 shadow self
    }];
}

- (void)testCase4_2_WeakifyOnlyUseSelf {
    // 4.2 只有 @weakify，无 @strongify，使用 self → ERROR
    @weakify(self);
    [self doSomethingWithBlock:^{
        [self doWork];  // ERROR: 应在 block 内添加 @strongify(self) 或使用 self_weak_
    }];
}

- (void)testCase4_3_WeakifyOnlyUseSelfWeak {
    // 4.3 只有 @weakify，无 @strongify，使用 self_weak_ → WARNING
    @weakify(self);
    [self doSomethingWithBlock:^{
        [self_weak_ doWork];  // WARNING: 建议添加 @strongify(self)
    }];
}

- (void)testCase4_4_WeakifyMultipleParams {
    // 4.4 @weakify 多参数
    id delegate = nil;
    @weakify(self, delegate);
    [self doBlock:^{
        @strongify(self, delegate);
        [self doWork];  // OK
    }];
}

// ===========================================
// 5. 混合使用（Manual + Macro）
// ===========================================

- (void)testCase5_3_MixedUsage {
    // 5.3 混用 manual 和 macro → WARNING
    __weak typeof(self) wSelf = self;
    @weakify(self);  // WARNING: 不建议混用 manual 和 macro 方式，请保持一致性
    [self doBlock:^{
        [wSelf doWork];
    }];
}

// ===========================================
// 6. 类方法（静态函数）中的 Block
// ===========================================

- (void)testCase6_1_UIViewAnimation {
    // 6.1 UIView 动画 - 系统类方法 → WARNING
    [UIView animateWithDuration:0.3 animations:^{
        self.completionBlock = nil;  // WARNING: 类方法中使用 self
    }];
}

- (void)testCase6_2_UIViewAnimationCompletion {
    // 6.2 UIView 带完成回调 → WARNING
    [UIView animateWithDuration:0.3 animations:^{
        self.completionBlock = nil;  // WARNING
    } completion:^(BOOL finished) {
        [self doWork];  // WARNING
    }];
}

- (void)testCase6_3_DispatchAsync {
    // 6.3 dispatch_async - C 函数 → WARNING
    dispatch_async(dispatch_get_main_queue(), ^{
        [self doWork];  // WARNING: C 函数通常不造成循环引用
    });
}

- (void)testCase6_4_DispatchAfter {
    // 6.4 GCD 延迟执行 → WARNING
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 1 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        [self doWork];  // WARNING: C 函数通常不造成循环引用
    });
}

- (void)testCase6_5_ClassMethodWithWeakStrong {
    // 6.5 类方法内正确使用 weak/strong → OK
    __weak typeof(self) wSelf = self;
    [UIView animateWithDuration:0.3 animations:^{
        __strong typeof(wSelf) sSelf = wSelf;
        if (!sSelf) return;
        [sSelf doWork];  // OK: 使用了正确的 weak/strong
    }];
}

// ===========================================
// 7. 其他边界情况
// ===========================================

- (void)testCase7_5_NSNotificationCenter {
    // 7.5 NSNotificationCenter
    [[NSNotificationCenter defaultCenter] addObserverForName:@"test" object:nil queue:nil usingBlock:^(NSNotification *note) {
        [self handleNotification:note];  // ERROR: 实例方法调用
    }];
}

// ===========================================
// 8. 正则匹配测试用例（各种格式）
// ===========================================

- (void)testCase8_1_NoSpaceWeak {
    // 8.1 无空格格式 - weak
    __weak typeof(self)weakMySelf = self;  // 应识别为 weak 声明
    [self doBlock:^{
        [weakMySelf doWork];  // WARNING
    }];
}

- (void)testCase8_2_NoSpaceStrong {
    // 8.2 无空格格式 - strong
    __weak typeof(self)wSelf = self;
    [self doBlock:^{
        __strong typeof(wSelf)strongMySelf = wSelf;  // 应识别为 strong 声明
        [strongMySelf doWork];  // OK
    }];
}

- (void)testCase8_3_ExtraSpaces {
    // 8.3 各种空格组合
    __weak  typeof(self)  wSelf  =  self;
    [self doBlock:^{
        [wSelf doWork];  // WARNING
    }];
}

// ===========================================
// 9. 不应报错的情况
// ===========================================

- (void)testCase9_1_NonSelfWeakReference {
    // 9.1 非 self 的 weak 引用
    id delegate = nil;
    __weak typeof(delegate) weakDelegate = delegate;
    [self doBlock:^{
        [weakDelegate doWork];  // OK: 不是 self 相关
    }];
}

- (void)testCase9_3_BlockOutsideSelf {
    // 9.3 block 外使用 self
    [self doWork];  // OK: 不在 block 内
}

- (void)testCase9_4_CommentedSelf {
    // 9.4 注释中的 self
    [self doBlock:^{
        // [self doWork];  // OK: 注释中的代码
        NSLog(@"test");
    }];
}

@end
