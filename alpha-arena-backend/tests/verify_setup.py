"""
Verification script to check if OpenAI API and all dependencies are properly configured
"""
import sys
import os

def check_environment():
    """Check if .env file exists and has OpenAI API key"""
    print("="*60)
    print("🔍 ENVIRONMENT CHECK")
    print("="*60)
    
    if not os.path.exists(".env"):
        print("❌ .env file not found!")
        return False
    
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.startswith("sk-"):
        print("❌ OPENAI_API_KEY not found or invalid in .env file!")
        return False
    
    print(f"✅ .env file found")
    print(f"✅ OpenAI API Key: {api_key[:15]}...")
    return True

def check_dependencies():
    """Check if all required packages are installed"""
    print("\n" + "="*60)
    print("📦 DEPENDENCIES CHECK")
    print("="*60)
    
    required_packages = [
        ("openai", "OpenAI"),
        ("ccxt", "CCXT"),
        ("pandas", "Pandas"),
        ("numpy", "NumPy"),
        ("dotenv", "python-dotenv"),
    ]
    
    all_ok = True
    for package, name in required_packages:
        try:
            module = __import__(package if package != "dotenv" else "dotenv")
            version = getattr(module, "__version__", "unknown")
            print(f"✅ {name}: {version}")
        except ImportError:
            print(f"❌ {name}: NOT INSTALLED")
            all_ok = False
    
    return all_ok

def check_openai_api():
    """Test OpenAI API connectivity"""
    print("\n" + "="*60)
    print("🤖 OPENAI API TEST")
    print("="*60)
    
    try:
        from openai import OpenAI
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Test API call
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'API test successful'"}],
            max_tokens=10
        )
        
        result = response.choices[0].message.content
        print(f"✅ OpenAI API is working!")
        print(f"✅ Response: {result}")
        return True
    except Exception as e:
        print(f"❌ OpenAI API error: {e}")
        return False

def check_agent_configs():
    """Check if agent configuration files exist"""
    print("\n" + "="*60)
    print("⚙️  AGENT CONFIGS CHECK")
    print("="*60)
    
    import json
    config_dir = "agents_config"
    config_files = ["apexalpha.json", "neuraquant.json", "visionx.json", 
                   "dataforge.json", "cortexzero.json"]
    
    all_exist = True
    for config_file in config_files:
        path = os.path.join(config_dir, config_file)
        if os.path.exists(path):
            with open(path) as f:
                config = json.load(f)
                agent_id = config.get("agent_id", "unknown")
                symbol = config.get("symbol", "unknown")
                print(f"✅ {config_file}: {agent_id} ({symbol})")
        else:
            print(f"❌ {config_file}: NOT FOUND")
            all_exist = False
    
    return all_exist

def main():
    """Run all checks"""
    print("\n🚀 KUSHAL SETUP VERIFICATION")
    print("="*60)
    
    checks = [
        ("Environment", check_environment),
        ("Dependencies", check_dependencies),
        ("OpenAI API", check_openai_api),
        ("Agent Configs", check_agent_configs)
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} check failed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    
    all_passed = True
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
        if not result:
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL CHECKS PASSED!")
        print("✅ You're ready to run the competition!")
        print("   Run: python main.py")
    else:
        print("❌ SOME CHECKS FAILED")
        print("   Please fix the issues above before running")
    print("="*60 + "\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())

