#!/usr/bin/env python3
"""
Setup script for Python Music Bot
"""

import os
import subprocess
import sys

def install_requirements():
    """Install required packages"""
    print("📦 Installing required packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Requirements installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing requirements: {e}")
        return False

def create_env_file():
    """Create .env file from template"""
    if os.path.exists('.env'):
        print("⚠️ .env file already exists, skipping creation")
        return True
    
    if os.path.exists('env_example.txt'):
        print("📝 Creating .env file from template...")
        try:
            with open('env_example.txt', 'r') as src:
                content = src.read()
            
            with open('.env', 'w') as dst:
                dst.write(content)
            
            print("✅ .env file created! Please edit it with your credentials.")
            return True
        except Exception as e:
            print(f"❌ Error creating .env file: {e}")
            return False
    else:
        print("❌ env_example.txt not found!")
        return False

def main():
    """Main setup function"""
    print("🎵 Python Music Bot Setup")
    print("=" * 30)
    
    # Install requirements
    if not install_requirements():
        print("❌ Setup failed at requirements installation")
        return False
    
    # Create .env file
    if not create_env_file():
        print("❌ Setup failed at .env file creation")
        return False
    
    print("\n✅ Setup completed successfully!")
    print("\n📋 Next steps:")
    print("1. Edit .env file with your Discord bot token")
    print("2. Add Spotify credentials (optional)")
    print("3. Run: python music_bot.py")
    print("\n🎵 Happy music botting!")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
