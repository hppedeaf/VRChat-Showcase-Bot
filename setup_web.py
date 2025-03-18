#!/usr/bin/env python3
"""
Setup script to create the necessary directory structure for the web application.
This script will create:
1. Directory structure
2. Basic placeholder files
"""
import os
import shutil
import sys

def create_directory(path):
    """Create directory if it doesn't exist."""
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Created directory: {path}")
    else:
        print(f"Directory already exists: {path}")

def create_file(path, content=""):
    """Create file with content if it doesn't exist."""
    if not os.path.exists(path):
        with open(path, 'w') as f:
            f.write(content)
        print(f"Created file: {path}")
    else:
        print(f"File already exists: {path}")

def main():
    """Main function to set up the web directory structure."""
    print("Setting up web directory structure...")
    
    # Create directories
    create_directory('web')
    create_directory('web/static')
    create_directory('web/static/css')
    create_directory('web/static/js')
    create_directory('web/static/img')
    create_directory('web/templates')
    
    # Create placeholder robots.txt
    robots_txt = """User-agent: *
Allow: /
Disallow: /api/
Disallow: /dashboard
Disallow: /guild/
Disallow: /callback
Disallow: /login
Disallow: /logout

Sitemap: https://vrchat-world-showcase.example.com/sitemap.xml"""
    create_file('web/static/robots.txt', robots_txt)
    
    # Create placeholder main.js
    main_js = """/**
 * Main JavaScript file for the VRChat World Showcase Bot
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('VRChat World Showcase Bot web interface loaded');
});"""
    create_file('web/static/js/main.js', main_js)
    
    # Create placeholder CSS files
    create_file('web/static/css/styles.css', '/* Main CSS for dashboard */')
    create_file('web/static/css/marketing-styles.css', '/* CSS for marketing pages */')
    
    # Create placeholder favicon - just a text file for now
    create_file('web/static/img/favicon.ico', '')
    
    print("\nSetup completed!")
    print("Next steps:")
    print("1. Copy your template files to web/templates/")
    print("2. Copy your CSS files to web/static/css/")
    print("3. Copy your JavaScript files to web/static/js/")
    print("4. Copy your images to web/static/img/")
    print("5. Run the server with 'python server.py'")

if __name__ == "__main__":
    main()