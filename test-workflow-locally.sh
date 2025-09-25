#!/bin/bash

# Local workflow testing script
# This script tests the key components of the GitHub Actions workflow locally

set -e

echo "🔍 Testing OpenStudio EE Gem Workflow Components Locally"
echo "========================================================"

# Test 1: Check Docker image availability
echo "1. Testing Docker image availability..."

# Check if images are already available locally
if docker images --format "table {{.Repository}}:{{.Tag}}" | grep -q "nrel/openstudio:develop"; then
    echo "✅ nrel/openstudio:develop image found locally"
    DOCKER_IMAGE="nrel/openstudio:develop"
elif docker images --format "table {{.Repository}}:{{.Tag}}" | grep -q "nrel/openstudio:3.10.0"; then
    echo "✅ nrel/openstudio:3.10.0 image found locally"
    DOCKER_IMAGE="nrel/openstudio:3.10.0"
else
    echo "⚠️  No local OpenStudio Docker images found. Attempting to pull..."
    
    # Try to pull the develop image
    if docker pull nrel/openstudio:develop 2>/dev/null; then
        echo "✅ Successfully pulled nrel/openstudio:develop image"
        DOCKER_IMAGE="nrel/openstudio:develop"
    else
        echo "❌ Failed to pull nrel/openstudio:develop image"
        echo "   This might be due to:"
        echo "   - Repository requires authentication (docker login)"
        echo "   - Network connectivity issues"
        echo "   - Repository access restrictions"
        
        # Try fallback to 3.10.0
        echo "   Trying fallback to nrel/openstudio:3.10.0..."
        if docker pull nrel/openstudio:3.10.0 2>/dev/null; then
            echo "✅ Successfully pulled nrel/openstudio:3.10.0 image"
            DOCKER_IMAGE="nrel/openstudio:3.10.0"
        else
            echo "❌ Failed to pull any OpenStudio Docker image"
            echo ""
            echo "🔧 To fix this issue:"
            echo "   1. Check if you need to run 'docker login' for private registries"
            echo "   2. Verify network connectivity to Docker Hub"
            echo "   3. Contact your system administrator about Docker registry access"
            echo ""
            echo "⏭️  Skipping Docker-based tests. The GitHub Actions workflow will"
            echo "   run in the GitHub environment which should have proper access."
            exit 0
        fi
    fi
fi

DOCKER_IMAGE="${DOCKER_IMAGE:-nrel/openstudio:develop}"
echo "Using Docker image: $DOCKER_IMAGE"

# Test 2: Run basic container commands
echo ""
echo "2. Testing basic container functionality..."
docker run --rm -v "$(pwd):/workspace" -w /workspace "$DOCKER_IMAGE" bash -c "
    echo 'Container started successfully'
    echo 'Ruby Version:' \$(ruby -v)
    echo 'Bundle Version:' \$(bundle -v)
    echo 'OpenStudio Version:' \$(openstudio openstudio_version)
    echo 'Listing OpenStudio Gems:' \$(openstudio gem_list)
"

# Test 3: Test locale setup
echo ""
echo "3. Testing locale configuration..."
docker run --rm -u root "$DOCKER_IMAGE" bash -c "
    apt-get update -qq
    apt-get install -y locales
    locale-gen en_US.UTF-8
    echo 'Locale setup completed'
    locale -a | grep en_US
"

# Test 4: Test bundle install
echo ""
echo "4. Testing bundle install..."
docker run --rm -v "$(pwd):/workspace" -w /workspace "$DOCKER_IMAGE" bash -c "
    if bundle install; then
        echo '✅ Bundle install successful'
        bundle list
    else
        echo '❌ Bundle install failed'
        exit 1
    fi
"

# Test 5: Test basic rake tasks (if available)
echo ""
echo "5. Testing rake tasks availability..."
docker run --rm -v "$(pwd):/workspace" -w /workspace "$DOCKER_IMAGE" bash -c "
    bundle install
    echo 'Available rake tasks:'
    bundle exec rake -T | head -10
"

# Test 6: Local environment validation (fallback if Docker fails)
if [ "$DOCKER_IMAGE" = "" ]; then
    echo ""
    echo "6. Testing local Ruby environment (Docker unavailable)..."
    
    # Check Ruby version
    if command -v ruby >/dev/null 2>&1; then
        echo "Ruby Version: $(ruby -v)"
    else
        echo "❌ Ruby not found in local environment"
    fi
    
    # Check Bundle version
    if command -v bundle >/dev/null 2>&1; then
        echo "Bundle Version: $(bundle -v)"
        
        # Test bundle install
        if bundle check >/dev/null 2>&1 || bundle install; then
            echo "✅ Bundle dependencies satisfied"
            
            # List available rake tasks
            echo "Available rake tasks:"
            bundle exec rake -T | head -5
        else
            echo "❌ Bundle install failed"
        fi
    else
        echo "❌ Bundler not found in local environment"
    fi
fi

echo ""
echo "🎉 Local workflow testing completed!"
echo ""
echo "📝 Notes:"
echo "   - Docker image testing completed (using $DOCKER_IMAGE)"
echo "   - All basic commands work as expected"
echo "   - Bundle install succeeds"
echo "   - Ready for GitHub Actions testing"
echo ""
echo "⚠️  To test the full workflow:"
echo "   1. Push changes to a test branch"
echo "   2. Monitor the GitHub Actions run"
echo "   3. Check the S3 bucket for uploaded results"
echo ""
echo "🔍 Alternative local testing (without Docker):"
echo "   If Docker testing failed, you can still validate the workflow logic:"
echo "   1. Check that bundle install works: bundle install"
echo "   2. List available rake tasks: bundle exec rake -T"
echo "   3. Test individual rake tasks if available"
echo "   4. The GitHub Actions environment should have proper Docker access"