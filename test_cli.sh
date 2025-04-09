#!/bin/bash

# test_cli.sh - Test script for TransitSync Routing CLI
# Created: April 2025
# Last modified: April 2025

# Remove 'set -e' to prevent script from exiting on first error
# We'll handle errors manually

echo "🔍 TransitSync Routing CLI Test Suite 🔍"
echo "========================================"
echo

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Make this script executable if it's not already
if [ ! -x "$0" ]; then
  chmod +x "$0"
  echo "✅ Made script executable"
fi

# Make sure main_cli.py is executable
if [ ! -x "main_cli.py" ]; then
  chmod +x main_cli.py
  echo "✅ Made main_cli.py executable"
fi

# Set home address for testing
HOME_ADDRESS="1 Willis Street, Wellington, New Zealand"

# Function to check network connectivity
check_connectivity() {
  echo -e "${BLUE}Checking network connectivity...${NC}"
  
  # Check OpenStreetMap Nominatim
  if curl -s --head --connect-timeout 5 https://nominatim.openstreetmap.org/ | grep "HTTP/" > /dev/null; then
    echo -e "✅ OpenStreetMap Nominatim: ${GREEN}Connected${NC}"
    osm_available=true
  else
    echo -e "❌ OpenStreetMap Nominatim: ${RED}Not Available${NC}"
    osm_available=false
  fi
  
  # Check local OTP server
  if curl -s --head --connect-timeout 2 http://localhost:8080/otp/index/graphql | grep "HTTP/" > /dev/null; then
    echo -e "✅ Local OTP Server: ${GREEN}Connected${NC}"
    otp_available=true
  else
    echo -e "❌ Local OTP Server: ${RED}Not Available${NC}"
    otp_available=false
  fi
  
  # Warn if both are unavailable
  if [ "$osm_available" = false ] && [ "$otp_available" = false ]; then
    echo -e "${RED}⚠️  WARNING: Major connectivity issues detected!${NC}"
    echo -e "${YELLOW}All tests will likely run in OFFLINE mode automatically.${NC}"
    echo -e "${YELLOW}If this is not intended, please check your network connection.${NC}"
    echo
    use_offline="--offline"
  elif [ "$otp_available" = false ]; then
    echo -e "${YELLOW}⚠️  Local OTP server is not available. Route planning will use OFFLINE mode.${NC}"
    echo
  fi
  
  sleep 1 # Give user time to read the message
}

# Function to print test header
run_test() {
  test_number=$1
  test_name=$2
  command=$3
  
  echo
  echo -e "${YELLOW}Test $test_number: $test_name${NC}"
  echo "----------------------------------------"
  
  # Run the command and capture the exit status
  eval "$command"
  status=$?
  
  # Print a status indicator
  if [ $status -eq 0 ]; then
    echo -e "\n${GREEN}✓ Test $test_number completed successfully${NC}"
  else
    echo -e "\n${RED}✗ Test $test_number encountered errors (exit code: $status)${NC}"
  fi
  
  echo
}

# Run connectivity check first
check_connectivity

# List of tests
run_all_tests() {
  run_test 1 "Checking help information" "./main_cli.py --help"
  
  run_test 2 "Testing geocoding" "./main_cli.py $use_offline geocode \"Wellington Central Library\""
  
  run_test 3 "Testing route planning" "./main_cli.py $use_offline route \"Victoria University, Wellington\" \"Wellington Zoo\" --time \"14:30\""
  
  run_test 4 "Testing route planning with current time" "./main_cli.py $use_offline route \"Wellington Train Station\" \"Zealandia\""
  
  run_test 5 "Testing full day planning with sample events" "./main_cli.py $use_offline plan events_sample.json --home \"$HOME_ADDRESS\""
  
  run_test 6 "Testing with debug mode" "./main_cli.py --debug $use_offline route \"Te Papa Museum\" \"Wellington Botanic Garden\" --time \"16:00\""
  
  run_test 7 "Testing in explicit offline mode" "./main_cli.py --offline plan events_sample.json"
  
  run_test 8 "Testing geocoding with non-existent location" "./main_cli.py $use_offline geocode \"NonExistentLocationXYZ\""
}

# If a test number is provided, run only that test
if [ ! -z "$1" ]; then
  case "$1" in
    1) run_test 1 "Checking help information" "./main_cli.py --help" ;;
    2) run_test 2 "Testing geocoding" "./main_cli.py $use_offline geocode \"Wellington Central Library\"" ;;
    3) run_test 3 "Testing route planning" "./main_cli.py $use_offline route \"Victoria University, Wellington\" \"Wellington Zoo\" --time \"14:30\"" ;;
    4) run_test 4 "Testing route planning with current time" "./main_cli.py $use_offline route \"Wellington Train Station\" \"Zealandia\"" ;;
    5) run_test 5 "Testing full day planning with sample events" "./main_cli.py $use_offline plan events_sample.json --home \"$HOME_ADDRESS\"" ;;
    6) run_test 6 "Testing with debug mode" "./main_cli.py --debug $use_offline route \"Te Papa Museum\" \"Wellington Botanic Garden\" --time \"16:00\"" ;;
    7) run_test 7 "Testing in explicit offline mode" "./main_cli.py --offline plan events_sample.json" ;;
    8) run_test 8 "Testing geocoding with non-existent location" "./main_cli.py $use_offline geocode \"NonExistentLocationXYZ\"" ;;
    check) check_connectivity ;;
    *) echo -e "${RED}Invalid test number: $1${NC}" ;;
  esac
else
  # Run all tests
  run_all_tests
  
  echo -e "${GREEN}All tests completed!${NC}"
  echo "You can modify this script to add more test cases or change parameters."
  echo
  echo "To run a specific test, you can use:"
  echo "./test_cli.sh [test_number]"
  echo
  echo "To check connectivity only:"
  echo "./test_cli.sh check"
fi