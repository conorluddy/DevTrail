#!/usr/bin/env python3
"""
GitHub Repository Contribution Exporter

This script extracts all of a user's contributions (PRs and commits) from a specific
GitHub repository over a specified time period and exports them to a structured JSON file.

Usage:
  python github-work-summary.py --repo owner/name [--timeframe days] [--output filename.json]
"""
#!/usr/bin/env python3
"""
GitHub Repository Contribution Exporter

This script extracts all of a user's contributions (PRs and commits) from a specific
GitHub repository over a specified time period and exports them to a structured JSON file.

Usage:
  python github-repo-export.py --repo owner/name [--timeframe days] [--output filename.json]
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta
import subprocess

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Export your GitHub contributions for a specific repository to JSON.'
    )
    parser.add_argument(
        '--repo',
        type=str,
        required=True,
        help='Repository in the format owner/name (e.g., microsoft/vscode)'
    )
    parser.add_argument(
        '--timeframe', 
        type=int, 
        default=365, 
        help='Number of days to look back (default: 365)'
    )
    parser.add_argument(
        '--output', 
        type=str, 
        default='github-repo-export.json', 
        help='Output JSON file (default: github-repo-export.json)'
    )
    parser.add_argument(
        '--username',
        type=str,
        help='GitHub username (optional, will try to detect automatically)'
    )
    return parser.parse_args()

def get_github_username_from_config():
    """Attempt to retrieve GitHub username from git config or SSH config"""
    try:
        # Try to get username from git config
        username = subprocess.check_output(
            ['git', 'config', 'github.user'], 
            universal_newlines=True
        ).strip()
        
        if username:
            return username
        
        # If not found in git config, try SSH config
        ssh_config = os.path.expanduser('~/.ssh/config')
        if os.path.exists(ssh_config):
            with open(ssh_config, 'r') as f:
                for line in f:
                    if 'User' in line and '@github.com' in line:
                        return line.split()[-1]
    except Exception:
        pass
    
    return None

def generate_github_token():
    """Generate a temporary GitHub token using GitHub CLI"""
    try:
        # Use GitHub CLI to authenticate and generate a token
        token = subprocess.check_output(
            ['gh', 'auth', 'token'], 
            universal_newlines=True
        ).strip()
        return token
    except Exception as e:
        print(f"Could not generate token: {e}")
        print("Please ensure GitHub CLI (gh) is installed and you're logged in.")
        print("Run 'gh auth login' to authenticate.")
        return None

def make_graphql_request(query, variables, token):
    """Make a GraphQL request to the GitHub API"""
    url = 'https://api.github.com/graphql'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    
    response = requests.post(
        url, 
        headers=headers,
        json={'query': query, 'variables': variables}
    )
    
    if response.status_code != 200:
        raise Exception(f"Query failed with status code {response.status_code}: {response.text}")
    
    result = response.json()
    if 'errors' in result:
        raise Exception(f"GraphQL query errors: {result['errors']}")
    
    return result['data']

def get_repository_info(owner, name, token):
    """Fetch repository information"""
    print(f"Fetching information for {owner}/{name}...")
    
    query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        nameWithOwner
        name
        description
        url
        isPrivate
        isArchived
      }
    }
    """
    
    variables = {
        'owner': owner,
        'name': name
    }
    
    data = make_graphql_request(query, variables, token)
    
    if not data.get('repository'):
        raise Exception(f"Repository {owner}/{name} not found or you don't have access to it.")
    
    return data['repository']

def get_user_pull_requests(username, owner, name, token, since_date):
    """Fetch pull requests created by the user in a specific repository"""
    print(f"Fetching pull requests created by {username} in {owner}/{name} since {since_date}...")
    
    # Convert since_date string to datetime object for filtering
    since_datetime = datetime.fromisoformat(since_date.replace('Z', '+00:00'))
    
    # First fetch all PRs in the repository and filter by author in the application
    query = """
    query($owner: String!, $name: String!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        pullRequests(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
          pageInfo {
            endCursor
            hasNextPage
          }
          nodes {
            title
            body
            url
            createdAt
            closedAt
            mergedAt
            state
            number
            author {
              login
            }
            additions
            deletions
            changedFiles
          }
        }
      }
    }
    """
    
    all_prs = []
    has_next_page = True
    cursor = None
    continue_fetching = True
    
    while has_next_page and continue_fetching:
        variables = {
            'owner': owner,
            'name': name,
            'cursor': cursor
        }
        
        data = make_graphql_request(query, variables, token)
        prs = data['repository']['pullRequests']['nodes']
        
        # Filter PRs by author and date
        for pr in prs:
            created_at = datetime.fromisoformat(pr['createdAt'].replace('Z', '+00:00'))
            
            # Check if this PR is by the target user and within the timeframe
            if pr['author'] and pr['author']['login'] == username and created_at >= since_datetime:
                all_prs.append(pr)
            elif created_at < since_datetime:
                # Since PRs are ordered by creation date, we can stop once we hit an old one
                continue_fetching = False
                break
        
        # Check if we need to fetch more pages
        if continue_fetching and data['repository']['pullRequests']['pageInfo']['hasNextPage']:
            cursor = data['repository']['pullRequests']['pageInfo']['endCursor']
        else:
            has_next_page = False
    
    print(f"Found {len(all_prs)} pull requests.")
    return all_prs

def get_user_commits(username, owner, name, token, since_date):
    """Fetch commits authored by the user for a specific repository"""
    print(f"Fetching commits by {username} in {owner}/{name} since {since_date}...")
    
    query = """
    query($owner: String!, $name: String!, $author: String!, $since: GitTimestamp, $cursor: String) {
      repository(owner: $owner, name: $name) {
        defaultBranchRef {
          target {
            ... on Commit {
              history(author: {emails: [$author]}, since: $since, first: 100, after: $cursor) {
                totalCount
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  oid
                  message
                  committedDate
                  url
                  additions
                  deletions
                  changedFiles
                  parents {
                    totalCount
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    
    # Try with different email formats since GitHub may use different emails for commits
    email_formats = [
        f"{username}@users.noreply.github.com",  # GitHub's noreply email
        username,  # Just the username (GitHub might infer it)
    ]
    
    all_commits = []
    
    for email in email_formats:
        has_next_page = True
        cursor = None
        
        while has_next_page:
            variables = {
                'owner': owner,
                'name': name,
                'author': email,
                'since': since_date,
                'cursor': cursor
            }
            
            try:
                data = make_graphql_request(query, variables, token)
                
                # Repository might not exist or user might not have access
                if not data.get('repository') or not data['repository'].get('defaultBranchRef'):
                    break
                
                commit_history = data['repository']['defaultBranchRef']['target']['history']
                commits = commit_history['nodes']
                
                all_commits.extend(commits)
                
                # Check for pagination
                has_next_page = commit_history['pageInfo']['hasNextPage']
                if has_next_page:
                    cursor = commit_history['pageInfo']['endCursor']
                
            except Exception as e:
                print(f"Error fetching commits with author {email}: {e}")
                has_next_page = False
    
    # Remove duplicates based on commit OID (SHA)
    unique_commits = []
    seen_oids = set()
    
    for commit in all_commits:
        if commit['oid'] not in seen_oids:
            seen_oids.add(commit['oid'])
            unique_commits.append(commit)
    
    print(f"Found {len(unique_commits)} unique commits.")
    return unique_commits

def main():
    """Main function to run the script"""
    args = parse_arguments()
    
    # Parse repository
    try:
        owner, name = args.repo.split('/')
    except ValueError:
        print("Error: Repository must be in the format 'owner/name'")
        sys.exit(1)
    
    # Get GitHub username
    username = args.username or get_github_username_from_config()
    if not username:
        username = input("Enter your GitHub username: ")
    
    # Generate token
    token = generate_github_token()
    if not token:
        sys.exit(1)
    
    # Calculate the date range
    since_date = (datetime.now() - timedelta(days=args.timeframe)).strftime('%Y-%m-%dT00:00:00Z')
    
    try:
        # Get repository info
        repository = get_repository_info(owner, name, token)
        
        # Get pull requests
        pull_requests = get_user_pull_requests(username, owner, name, token, since_date)
        
        # Get commits
        commits = get_user_commits(username, owner, name, token, since_date)
        
        # Prepare the output
        result = {
            'username': username,
            'repository': repository,
            'generated_at': datetime.now().isoformat(),
            'timeframe_days': args.timeframe,
            'since_date': since_date,
            'statistics': {
                'total_pull_requests': len(pull_requests),
                'total_commits': len(commits),
            },
            'pull_requests': pull_requests,
            'commits': commits
        }
        
        # Save to file
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\nRepository contribution export completed successfully to {args.output}")
        print(f"Found {len(pull_requests)} PRs and {len(commits)} commits in {repository['nameWithOwner']}.")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()