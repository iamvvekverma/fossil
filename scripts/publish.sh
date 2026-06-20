#!/usr/bin/env bash
# fossil — One-shot GitHub publishing script
# Run this after authenticating with: gh auth login
set -euo pipefail

echo "🦴 fossil — Publishing to GitHub"
echo "================================"

# Check gh auth
if ! gh auth status &>/dev/null; then
    echo "❌ Not authenticated. Run: gh auth login"
    exit 1
fi

echo "✅ GitHub CLI authenticated"

# Create the repo
echo ""
echo "📦 Creating GitHub repository..."
gh repo create fossil \
    --public \
    --description "Dead-code forensics CLI — find dead code, understand why it died, and safely delete it." \
    --source . \
    --push

echo "✅ Repository created and pushed"

# Set topics
echo ""
echo "🏷️  Setting repository topics..."
gh repo edit --add-topic dead-code,static-analysis,cli,python,developer-tools,git,forensics,code-quality

echo "✅ Topics set"

# Enable discussions
echo ""
echo "💬 Enabling discussions..."
gh repo edit --enable-discussions

echo ""
echo "🎉 Repository is live!"
echo ""
echo "📋 Next steps:"
echo "   1. Visit: https://github.com/$(gh api user --jq .login)/fossil"
echo "   2. Tag the release: git tag v0.2.0 && git push origin v0.2.0"
echo "   3. Configure PyPI trusted publishing in GitHub Settings → Environments"
echo "   4. Post on HN/Reddit/X (see shipping_guide.md for templates)"
