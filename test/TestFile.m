//
//  TestFile.m
//  测试文件 - 包含各种违规示例
//

#import <Foundation/Foundation.h>

// 违规: 类名没有前缀
@interface testClass : NSObject

// 违规: delegate 没有使用 weak
@property (nonatomic, strong) id<NSCopying> delegate;

// 违规: 属性名首字母大写
@property (nonatomic, strong) NSString *UserName;

// 正确
@property (nonatomic, weak) id<NSCopying> safeDelegate;

@end

@implementation testClass

// 违规: 方法名首字母大写
- (void)DoSomething {
    // 违规: 行太长
    NSString *veryLongVariableName = @"This is a very very very very very very very very very very long string that exceeds the line length limit";

    // 违规: 硬编码密码
    NSString *password = @"secretPassword123";

    // 违规: 不安全的 API
    char buffer[100];
    strcpy(buffer, "test");

    // 违规: block 中直接使用 self
    dispatch_async(dispatch_get_main_queue(), ^{
        [self doAnotherThing];
    });

    // TODO: 这里需要优化
    // FIXME: 这个逻辑有问题

    NSLog(@"test"); // 可能被禁用
}

- (void)doAnotherThing {
    // 正确的 block 使用方式
    __weak typeof(self) weakSelf = self;
    dispatch_async(dispatch_get_main_queue(), ^{
        __strong typeof(weakSelf) strongSelf = weakSelf;
        if (strongSelf) {
            // do something
        }
    });
}

// 违规: 方法太长（示例）
- (void)veryLongMethod {
    NSLog(@"line 1");
    NSLog(@"line 2");
    NSLog(@"line 3");
    NSLog(@"line 4");
    NSLog(@"line 5");
    NSLog(@"line 6");
    NSLog(@"line 7");
    NSLog(@"line 8");
    NSLog(@"line 9");
    NSLog(@"line 10");
    // ... 假设这里有更多行
}

@end
