# GitLab Repository Setup Guide

This guide will help you create a GitLab repository and push the E-Commerce Agent Workshop.

---

## Option 1: Create GitLab Repo via Web UI (Recommended)

### Step 1: Create Repository on GitLab

1. **Go to GitLab** (https://gitlab.com or your GitLab instance)
2. **Click "New Project"**
3. **Select "Create blank project"**
4. **Fill in project details:**
   - **Project name:** `ecommerce-agent-workshop` (or your preferred name)
   - **Project URL:** Choose your namespace (username or group)
   - **Visibility Level:**
     - Private (recommended for workshop materials)
     - Internal (if using GitLab Enterprise)
     - Public (if you want it open source)
   - **Initialize repository with a README:** ❌ UNCHECK (we have our own)
5. **Click "Create project"**

### Step 2: Copy the Repository URL

After creation, you'll see a page with the clone URL. Copy it:
```
# HTTPS (easier, no SSH key needed)
https://gitlab.com/your-username/ecommerce-agent-workshop.git

# SSH (if you have SSH keys configured)
git@gitlab.com:your-username/ecommerce-agent-workshop.git
```

---

## Option 2: Create GitLab Repo via CLI

If you have GitLab CLI (`glab`) installed:

```bash
# Install glab (if not installed)
# macOS
brew install glab

# Authenticate
glab auth login

# Create repository
glab repo create ecommerce-agent-workshop \
  --private \
  --description "Multi-Agent E-Commerce Customer Service Workshop"
```

---

## Push Workshop to GitLab

### Step 1: Initialize Git Repository

```bash
# Navigate to workshop directory
cd /Users/mmelli/Library/CloudStorage/OneDrive-amazon.com/GenAI-SSA/github/ecommerce-agent-workshop

# Initialize git repository (if not already initialized)
git init

# Check current status
git status
```

### Step 2: Add Remote Repository

Replace `YOUR_GITLAB_URL` with the URL you copied from GitLab:

```bash
# Add GitLab as remote
git remote add origin YOUR_GITLAB_URL

# Example with HTTPS:
git remote add origin https://gitlab.com/your-username/ecommerce-agent-workshop.git

# Example with SSH:
git remote add origin git@gitlab.com:your-username/ecommerce-agent-workshop.git

# Verify remote was added
git remote -v
```

### Step 3: Stage All Files

```bash
# Add all files (respects .gitignore)
git add .

# Review what will be committed
git status
```

### Step 4: Create Initial Commit

```bash
# Commit with descriptive message
git commit -m "Initial commit: E-Commerce Multi-Agent Workshop

- Module 0: Prerequisites with automated infrastructure setup
- Module 1: Multi-agent prototype with cost optimization
- Module 2: Evaluation framework with custom evaluators
- Complete validation and testing
- Comprehensive documentation"
```

### Step 5: Push to GitLab

```bash
# Push to GitLab (main branch)
git push -u origin main

# If your default branch is 'master', use:
# git push -u origin master
```

If you get an error about branch name, set it explicitly:
```bash
# Set main as default branch
git branch -M main
git push -u origin main
```

---

## Authentication Options

### Option A: HTTPS with Personal Access Token (Recommended)

1. **Create Personal Access Token:**
   - Go to GitLab → Settings → Access Tokens
   - Name: `Workshop Repository Access`
   - Scopes: ✅ `read_repository`, ✅ `write_repository`
   - Click "Create personal access token"
   - **COPY THE TOKEN** (you won't see it again!)

2. **Use token when prompted:**
   ```bash
   git push -u origin main
   # Username: your-username
   # Password: <paste-your-token>
   ```

3. **Store credentials (optional):**
   ```bash
   # Cache credentials for 1 hour
   git config --global credential.helper 'cache --timeout=3600'

   # Or store permanently (less secure)
   git config --global credential.helper store
   ```

### Option B: SSH Key Authentication

If you already have SSH keys configured:

```bash
# Verify SSH key is added to GitLab
ssh -T git@gitlab.com

# Should see: "Welcome to GitLab, @your-username!"
```

If not configured, see: https://docs.gitlab.com/ee/user/ssh.html

---

## Verify Upload

### Check on GitLab Web Interface

1. Go to your GitLab repository URL
2. Verify all files are present:
   ```
   ✅ 00-prerequisites/
   ✅ 01-multi-agent-prototype/
   ✅ 02-evaluation-baseline/
   ✅ README.md
   ✅ QUICK_START.md
   ✅ WORKSHOP_VALIDATION_COMPLETE.md
   ✅ All other files
   ```

### Check from Command Line

```bash
# View remote repository info
git remote show origin

# View last commit
git log -1

# View all branches
git branch -a
```

---

## Repository Structure

Your GitLab repository will have this structure:

```
ecommerce-agent-workshop/
├── .gitignore                           # Excludes unnecessary files
├── README.md                            # Main workshop overview
├── QUICK_START.md                       # Getting started guide
├── WORKSHOP_VALIDATION_COMPLETE.md      # Validation report
├── GITLAB_SETUP.md                      # This file
├── EVALUATION_FIXES_SUMMARY.md          # Module 2 API guide
│
├── 00-prerequisites/
│   ├── README.md
│   ├── requirements.txt
│   ├── setup_infrastructure.py          # Automated setup
│   ├── verify_infrastructure.py         # Validation script
│   └── sample_data/                     # JSON data files
│       ├── orders_sample.json
│       ├── accounts_sample.json
│       └── products.json
│
├── 01-multi-agent-prototype/
│   ├── 01-multi-agent-prototype.ipynb   # Main notebook
│   ├── test_notebook_fixes.py           # Test script
│   ├── tools/                           # Tool implementations
│   │   ├── order_tools.py
│   │   ├── product_tools.py
│   │   └── account_tools.py
│   └── agents/                          # Agent implementations
│       ├── order_agent.py
│       ├── product_agent.py
│       ├── account_agent.py
│       └── orchestrator.py
│
└── 02-evaluation-baseline/
    ├── 02-evaluation-baseline.ipynb     # Evaluation notebook
    ├── custom_evaluators.py             # Custom evaluators
    ├── evaluation_dataset.json          # Test cases
    ├── test_evaluation_fixes.py         # Test script
    ├── EVALUATION_FIXES_SUMMARY.md      # API guide
    └── VALIDATION_SUMMARY.md            # Validation report
```

---

## Additional Git Operations

### Create Development Branch

```bash
# Create and switch to dev branch
git checkout -b development

# Make changes, then commit
git add .
git commit -m "Description of changes"

# Push dev branch to GitLab
git push -u origin development
```

### Tag a Release

```bash
# Create annotated tag
git tag -a v1.0.0 -m "Workshop v1.0.0 - Initial Release
- Complete multi-agent prototype
- Evaluation framework
- Validated and tested"

# Push tag to GitLab
git push origin v1.0.0

# Or push all tags
git push --tags
```

### Update Repository

```bash
# After making local changes
git add .
git commit -m "Description of changes"
git push
```

---

## GitLab Features to Enable

### 1. Enable GitLab CI/CD (Optional)

Create `.gitlab-ci.yml` in repository root:

```yaml
# Example CI/CD pipeline
image: python:3.10

stages:
  - test

test_infrastructure:
  stage: test
  script:
    - pip install -r 00-prerequisites/requirements.txt
    - cd 00-prerequisites
    - python verify_infrastructure.py || echo "Skipping infra check in CI"

test_module1:
  stage: test
  script:
    - pip install -r 00-prerequisites/requirements.txt
    - cd 01-multi-agent-prototype
    - python test_notebook_fixes.py || echo "Skipping Module 1 test (requires AWS)"

test_module2:
  stage: test
  script:
    - pip install -r 00-prerequisites/requirements.txt
    - cd 02-evaluation-baseline
    - python test_evaluation_fixes.py || echo "Skipping Module 2 test (requires AWS)"
```

### 2. Enable Wiki (Optional)

Use GitLab Wiki for:
- Workshop facilitation guide
- Troubleshooting FAQ
- Participant notes

### 3. Set Up Protected Branches

Protect `main` branch:
- Settings → Repository → Protected Branches
- Add `main` branch
- Allowed to merge: Maintainers
- Allowed to push: No one

### 4. Add Repository Description

- Settings → General
- Project description: "Production-ready multi-agent customer service system workshop using AWS Bedrock and Strands Agent SDK"
- Topics/Tags: `aws`, `bedrock`, `multi-agent`, `claude`, `strands`, `workshop`

---

## Sharing the Workshop

### Public Repository

If you made it public, share the URL:
```
https://gitlab.com/your-username/ecommerce-agent-workshop
```

### Private Repository

Add collaborators:
1. Go to: Settings → Members
2. Click "Invite members"
3. Enter email or username
4. Select role: Developer or Maintainer
5. Click "Invite"

### Clone Instructions for Participants

Provide these instructions to workshop participants:

```bash
# Clone the repository
git clone https://gitlab.com/your-username/ecommerce-agent-workshop.git
cd ecommerce-agent-workshop

# Follow the Quick Start guide
cat QUICK_START.md
```

---

## Troubleshooting

### Issue: "remote: Repository not found"

**Solution:** Verify repository URL and permissions
```bash
git remote -v
# Update if needed:
git remote set-url origin YOUR_CORRECT_URL
```

### Issue: "failed to push some refs"

**Solution:** Pull latest changes first
```bash
git pull origin main --rebase
git push origin main
```

### Issue: "Authentication failed"

**Solution:**
- Check Personal Access Token has correct scopes
- Verify username is correct
- Try SSH instead of HTTPS (or vice versa)

### Issue: Files not tracked

**Solution:** Check if excluded by .gitignore
```bash
git status --ignored
git check-ignore -v <filename>
```

---

## Best Practices

✅ **Commit Message Format:**
```
<type>: <subject>

<body>

<footer>
```

Example:
```
feat: Add custom routing accuracy evaluator

- Implements LLM-as-judge pattern for agent routing
- Uses Claude Haiku 4.5 for cost efficiency
- Includes rubric for multi-agent scenarios

Closes #42
```

✅ **Commit Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Adding tests
- `refactor`: Code refactoring
- `chore`: Maintenance tasks

✅ **Branch Naming:**
- `feature/add-module-3`
- `fix/notebook-formatting`
- `docs/update-readme`

---

## Next Steps

After pushing to GitLab:

1. ✅ **Add README badges** (build status, coverage)
2. ✅ **Set up CI/CD pipeline** for automated testing
3. ✅ **Create GitLab Issues** for future enhancements
4. ✅ **Add project milestones** for module releases
5. ✅ **Enable GitLab Pages** for documentation hosting

---

## Summary

You now have:
- ✅ Complete workshop in GitLab repository
- ✅ Proper .gitignore to exclude unnecessary files
- ✅ All documentation and code tracked
- ✅ Ready to share with participants

**Need help?** Check GitLab documentation: https://docs.gitlab.com
