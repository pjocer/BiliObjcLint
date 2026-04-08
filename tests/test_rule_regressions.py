import sys
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core.lint.config import RuleConfig
from core.lint.rules.memory_rules.block_retain_cycle_rule import BlockRetainCycleRule
from core.lint.rules.memory_rules.collection_mutation_rule import CollectionMutationRule
from core.lint.rules.memory_rules.wrapper_empty_pointer_rule import WrapperEmptyPointerRule


def run_rule(rule, source: str):
    content = textwrap.dedent(source).lstrip("\n")
    lines = content.splitlines()
    return rule.check(
        file_path="/tmp/TestFile.m",
        content=content,
        lines=lines,
        changed_lines=set(),
    )


class WrapperEmptyPointerRuleRegressionTests(unittest.TestCase):
    def test_skips_safe_multiline_message_fragments_and_local_nonnull_values(self):
        violations = run_rule(
            WrapperEmptyPointerRule(RuleConfig()),
            """
            @implementation Demo
            - (NSObject *)safeFieldWithPlaceholder:(NSString *)placeholder
                                       defaultText:(NSString *)defaultText {
                NSObject *field = [NSObject new];
                return field;
            }

            - (void)testWrapper {
                NSObject *tfc = [NSObject new];
                NSArray *first = @[[self safeFieldWithPlaceholder:@"a"
                                                     defaultText:@""]];
                __strong typeof(self) strongSelf = self;
                NSArray *second = @[[strongSelf safeFieldWithPlaceholder:@"b" defaultText:@""]];
                NSArray *third = @[tfc];
            }
            @end
            """,
        )

        self.assertEqual([], violations)


class CollectionMutationRuleRegressionTests(unittest.TestCase):
    def test_accepts_safe_local_function_calls_and_guarded_casts(self):
        violations = run_rule(
            CollectionMutationRule(RuleConfig()),
            """
            static NSString *SafeTitle(NSUInteger value) {
                return @"ok";
            }

            @implementation Demo
            - (void)testCollection {
                NSMutableArray *titles = [NSMutableArray array];
                [titles addObject:SafeTitle(1)];

                NSArray *values = @[@"ok"];
                NSMutableOrderedSet *ids = [NSMutableOrderedSet orderedSet];
                for (id item in values) {
                    if ([item isKindOfClass:[NSString class]]) {
                        [ids addObject:(NSString *)item];
                    }
                }
            }
            @end
            """,
        )

        self.assertEqual([], violations)


class BlockRetainCycleRuleRegressionTests(unittest.TestCase):
    def test_ignores_self_outside_block_but_warns_for_class_method_blocks(self):
        violations = run_rule(
            BlockRetainCycleRule(RuleConfig()),
            """
            @implementation Demo
            - (void)methodWithBlockParam:(void (^)(NSData *imageData))completion {
                NSObject *proxy = [self helper];
                [proxy presentOn:self];
            }

            - (void)showAlert {
                [DemoAlertViewController alertControllerWithConfig:nil completion:^(id result) {
                    [self submit];
                }];
            }
            @end
            """,
        )

        self.assertEqual(1, len(violations))
        self.assertEqual("class_method_self", violations[0].sub_type)
        self.assertEqual(9, violations[0].line)


if __name__ == "__main__":
    unittest.main()
