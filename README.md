<p align="center">
  <h1 align="center">BiliObjCLint</h1>
  <p align="center">Objective-C Code Linting Tool with Xcode Integration and Claude AI Auto-fix</p>
  <p align="center">
    <a href="README.md">English</a> | <a href="README.zh-CN.md">简体中文</a>
  </p>
</p>

---

## Features

- **Incremental Check**: Only check Git-changed code for fast and efficient linting
- **Xcode Integration**: Output native Xcode warning/error format
- **Dual Engine Architecture**:
  - OCLint: 70+ built-in rules with deep AST analysis
  - Python Rule Engine: Lightweight, fast, and easy to extend
- **Claude AI Auto-fix**: Automatically fix code issues with Claude Code CLI
- **Highly Configurable**: YAML configuration file for flexible rule customization
- **Easy to Extend**: Support both Python and C++ custom rules

## Requirements

- macOS 10.15+
- Python 3.9+
- Xcode 12+ (for Xcode integration)
- Git (for incremental checking)

## Installation

### Via Homebrew (Recommended)

```bash
# Add tap and install
brew tap pjocer/biliobjclint
brew install biliobjclint

# Update to latest version
brew update && brew upgrade biliobjclint
```

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/pjocer/BiliObjcLint.git
cd BiliObjcLint

# Initialize Python virtual environment
./scripts/setup_env.sh
```

## Quick Start

### 1. Basic Usage

```bash
# Check all files
biliobjclint

# Incremental check (only Git changes)
biliobjclint --incremental

# Check specific files
biliobjclint --files path/to/File.m

# Verbose output
biliobjclint --verbose
```

### 2. Xcode Integration

```bash
# For .xcodeproj
biliobjclint-xcode /path/to/App.xcodeproj

# For .xcworkspace (specify project name)
biliobjclint-xcode /path/to/App.xcworkspace -p MyProject

# Specify target
biliobjclint-xcode /path/to/App.xcworkspace -p MyProject -t MyTarget

# List available projects in workspace
biliobjclint-xcode /path/to/App.xcworkspace --list-projects

# List available targets
biliobjclint-xcode /path/to/App.xcodeproj --list-targets
```

This will:
1. Add a Build Phase script to your Xcode project
2. Copy the default configuration file to your project root

### 3. Bootstrap Script (Auto Install)

Use the bootstrap script to automatically install and configure BiliObjCLint:

**Step 1: Copy bootstrap.sh to your project**
```bash
mkdir -p /path/to/your/project/scripts
cp $(brew --prefix)/share/biliobjclint/scripts/bootstrap.sh /path/to/your/project/scripts/
```

**Step 2: Add Build Phase in Xcode**
1. Open your `.xcworkspace` or `.xcodeproj` in Xcode
2. Select your project in the navigator
3. Select the target you want to add linting to
4. Go to **Build Phases** tab
5. Click **+** → **New Run Script Phase**
6. Drag the new phase to the **top** (before all other phases)
7. Paste the following script:
```bash
"${SRCROOT}/scripts/bootstrap.sh" -w "${WORKSPACE_PATH}" -p "${PROJECT_FILE_PATH}" -t "${TARGET_NAME}"
```
> Note: `${WORKSPACE_PATH}` is the workspace full path, `${PROJECT_FILE_PATH}` is the .xcodeproj full path

**What the bootstrap script does:**
1. Check if BiliObjCLint is installed, install via Homebrew if not
2. Check if Lint Phase exists, install if not
3. Check if Lint Phase needs update, update automatically

### 4. Install OCLint (Optional)

If you need OCLint's deep AST analysis:

```bash
brew install oclint
```

## Configuration

Create `.biliobjclint.yaml` in your project root:

```yaml
# Basic settings
base_branch: "origin/master"
incremental: true
fail_on_error: true

# File filtering
excluded:
  - "Pods/**"
  - "Vendor/**"
  - "ThirdParty/**"

# Python rules
python_rules:
  class_prefix:
    enabled: true
    severity: warning
    params:
      prefix: "BL"

  weak_delegate:
    enabled: true
    severity: error

  line_length:
    enabled: true
    params:
      max_length: 120

# OCLint settings
oclint:
  enabled: true
  rule_configurations:
    - key: LONG_METHOD
      value: 80
    - key: CYCLOMATIC_COMPLEXITY
      value: 10

# Claude auto-fix settings
claude_autofix:
  trigger: "any"     # any | error | disable
  mode: "silent"     # silent | terminal | vscode
  timeout: 120
```

See `config/default.yaml` for a complete example.

## Built-in Rules

### Python Rules

| Rule ID | Description | Default Severity |
|---------|-------------|------------------|
| `class_prefix` | Class name prefix check | warning |
| `property_naming` | Property naming (lowerCamelCase) | warning |
| `constant_naming` | Constant naming check | warning |
| `method_naming` | Method naming check | warning |
| `line_length` | Line length limit | warning |
| `method_length` | Method length limit | warning |
| `todo_fixme` | TODO/FIXME detection | warning |
| `weak_delegate` | Delegate should use weak | error |
| `block_retain_cycle` | Block retain cycle detection | warning |
| `forbidden_api` | Forbidden API check | error |
| `hardcoded_credentials` | Hardcoded credentials detection | error |

### OCLint Rules

OCLint provides 70+ rules in categories: Basic, Convention, Empty, Naming, Redundant, Size, Unused.

## Command Line Options

```
biliobjclint [options]

Options:
  --config, -c PATH       Configuration file path
  --project-root, -p PATH Project root directory
  --incremental, -i       Incremental check mode
  --base-branch, -b NAME  Base branch for incremental comparison
  --files, -f FILE...     Specific files to check
  --xcode-output, -x      Xcode format output (default)
  --json-output, -j       JSON format output
  --no-oclint             Disable OCLint
  --no-python-rules       Disable Python rules
  --verbose, -v           Verbose output
```

## FAQ

### Q: How to check only specific types of issues?

Configure `.biliobjclint.yaml` to disable unwanted rules:

```yaml
python_rules:
  todo_fixme:
    enabled: false
```

### Q: How to ignore specific files?

Add exclusion patterns in the configuration:

```yaml
excluded:
  - "**/*Generated*.m"
  - "Legacy/**"
```

### Q: OCLint build fails?

Use Python rules only:

```bash
biliobjclint --no-oclint
```

### Q: How to use Claude auto-fix?

1. Install [Claude Code CLI](https://claude.ai/code)
2. Configure in `.biliobjclint.yaml`:

```yaml
claude_autofix:
  trigger: "any"
  mode: "silent"
```

## Documentation

| Document | Description |
|----------|-------------|
| [Custom Rules](docs/CUSTOM_RULES.md) | How to create custom lint rules |
| [Development](docs/DEVELOPMENT.md) | Project structure and development guide |
| [Release](docs/RELEASE.md) | Version release workflow |

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

This project includes OCLint, which is licensed under the BSD 3-Clause License.
