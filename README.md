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
- **Python Rule Engine**: Lightweight, fast, and easy to extend
- **Claude AI Auto-fix**: Automatically fix code issues with Claude Code CLI
- **Highly Configurable**: YAML configuration file for flexible rule customization
- **Easy to Extend**: Support custom Python rules

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
./setup_env.sh
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

### 3. Auto Bootstrap Mode (Recommended for Multi-Project Workspaces)

Automatically copy bootstrap.sh and inject Package Manager Build Phase with correct relative paths:

```bash
# For workspace (recommended for complex project structures)
biliobjclint-xcode /path/to/App.xcworkspace -p MyProject -t MyTarget --bootstrap

# For xcodeproj
biliobjclint-xcode /path/to/App.xcodeproj -t MyTarget --bootstrap

# Preview changes without applying
biliobjclint-xcode /path/to/App.xcworkspace -p MyProject -t MyTarget --bootstrap --dry-run
```

This will:
1. Copy `bootstrap.sh` to `./.biliobjclint/` directory (same level as workspace/xcodeproj)
2. Calculate correct relative path from SRCROOT to `.biliobjclint` directory
3. Add `[BiliObjcLint] Package Manager` Build Phase with auto-calculated paths

This is especially useful for workspaces where SRCROOT differs from the workspace root directory.

### 4. Bootstrap Script (Manual Setup)

Use the bootstrap script to automatically install and configure BiliObjCLint:

**Step 1: Copy bootstrap.sh to your project**
```bash
mkdir -p /path/to/your/project/.biliobjclint
cp $(brew --prefix biliobjclint)/libexec/config/bootstrap.sh /path/to/your/project/.biliobjclint/
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
"${SRCROOT}/.biliobjclint/bootstrap.sh" -w "${WORKSPACE_PATH}" -p "${PROJECT_FILE_PATH}" -t "${TARGET_NAME}"
```
> Note: `${WORKSPACE_PATH}` is the workspace full path, `${PROJECT_FILE_PATH}` is the .xcodeproj full path

**What the bootstrap script does:**
1. Check if BiliObjCLint is installed, install via Homebrew if not
2. Silently check for new versions in background (every 24 hours via GitHub Tags API, non-blocking)
3. Auto-upgrade via `brew upgrade` when new version found, show system notification with version and changelog
4. Check if Lint Build Phase exists, inject if not
5. Check Lint Build Phase version, auto-upgrade script if outdated

> 💡 **About auto-update detection:**
> - State file is located at `~/.biliobjclint_update_state`, recording the last check time
> - By default, checks for new versions every 24 hours to avoid frequent GitHub API requests
> - To force an immediate update check, delete the state file: `rm -f ~/.biliobjclint_update_state`
> - After update completes, a macOS system notification will show the new version and changelog

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
| `method_parameter` | Method parameter count check (default max: 4) | warning |
| `line_length` | Line length limit | warning |
| `method_length` | Method length limit | warning |
| `todo_fixme` | TODO/FIXME detection | warning |
| `weak_delegate` | Delegate should use weak | error |
| `block_retain_cycle` | Block retain cycle detection (includes weak/strong self check) | warning |
| `wrapper_empty_pointer` | Container literal nil value check | warning |
| `dict_usage` | Dictionary setObject:forKey: usage check | warning |
| `collection_mutation` | Collection mutation safety check | warning |
| `forbidden_api` | Forbidden API check | error |
| `hardcoded_credentials` | Hardcoded credentials detection | error |
| `insecure_random` | Insecure random number generation detection | warning |
| `file_header` | File header comment check | warning |

## Command Line Options

### biliobjclint

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
  --no-python-rules       Disable Python rules
  --verbose, -v           Verbose output
```

### biliobjclint-xcode

```
biliobjclint-xcode <project_path> [options]

Options:
  --project, -p NAME      Project name (for workspace)
  --target, -t NAME       Target name (default: main target)
  --remove                Remove Lint Phase
  --bootstrap             Copy bootstrap.sh and inject Package Manager Build Phase
  --check-update          Check if injected script needs update
  --list-projects         List all projects in workspace
  --list-targets          List all available targets
  --dry-run               Show changes without applying
  --override              Force override existing Lint Phase
```

### biliobjclint-server

Local statistics server with dashboard for visualizing lint metrics.

```
biliobjclint-server <action> [options]

Actions:
  start                   Start server in background
  stop                    Stop running server
  restart                 Restart server
  status                  Show server status
  run                     Run server in foreground
  clear                   Clear all local data

Options:
  --config PATH           Config file path
  --yes, -y               Skip confirmation for clear
```

**Usage Example:**

```bash
# Start server
biliobjclint-server start

# Check status
biliobjclint-server status

# View dashboard (default: http://127.0.0.1:18080/login)
```

**Client Configuration** (add to `.biliobjclint.yaml`):

```yaml
metrics:
  enabled: true
  endpoint: "http://127.0.0.1:18080"
```

**Features:**
- Real-time lint metrics dashboard
- Rule violation statistics and trends
- User authentication and management
- Historical data visualization

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

### Q: How to use Claude auto-fix?

1. Install [Claude Code CLI](https://claude.ai/code)
2. Configure Claude environment variables in `~/.zshrc` or `~/.bashrc`:

```bash
# Required: API endpoint and authentication
export ANTHROPIC_BASE_URL=https://api.anthropic.com  # or your custom endpoint
export ANTHROPIC_AUTH_TOKEN=your-api-key-here

# Optional: Model and timeout settings
export ANTHROPIC_MODEL=claude-4.5-opus
export API_TIMEOUT_MS=600000
```

> **Important**: These environment variables must be configured in your shell config file (`.zshrc` or `.bashrc`), as Xcode Build Phase runs as a background process that doesn't inherit your terminal session environment.

3. Configure in `.biliobjclint.yaml`:

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
