#!/usr/bin/env python3
"""
GitHub Collaboration Analyzer

This script extracts a user's collaborative contributions in a specific repository,
including PR reviews, comments, and discussions.

Usage:
  python github-collaboration-export.py --repo owner/name [--timeframe days] [--output filename.json]

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
        description='Export your GitHub collaborative contributions for a specific repository to JSON.'
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
        default='github-collaboration-export.json', 
        help='Output JSON file (default: github-collaboration-export.json)'
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

def get_user_pr_reviews(username, owner, name, token, since_date):
    """Fetch PRs reviewed by the user in a specific repository"""
    print(f"Fetching PRs reviewed by {username} in {owner}/{name} since {since_date}...")
    
    since_datetime = datetime.fromisoformat(since_date.replace('Z', '+00:00'))
    
    query = """
    query($owner: String!, $name: String!, $username: String!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        pullRequests(first: 100, after: $cursor, states: [OPEN, CLOSED, MERGED]) {
          pageInfo {
            endCursor
            hasNextPage
          }
          nodes {
            number
            title
            url
            createdAt
            author {
              login
            }
            reviews(first: 10, author: $username) {
              nodes {
                state
                body
                createdAt
                url
                comments(first: 30) {
                  totalCount
                  nodes {
                    body
                    path
                    position
                    createdAt
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    
    reviewed_prs = []
    has_next_page = True
    cursor = None
    
    while has_next_page:
        variables = {
            'owner': owner,
            'name': name,
            'username': username,
            'cursor': cursor
        }
        
        data = make_graphql_request(query, variables, token)
        prs = data['repository']['pullRequests']['nodes']
        
        # Find PRs with reviews by this user
        for pr in prs:
            reviews = pr['reviews']['nodes']
            if reviews:
                # Skip PRs authored by the user - we'll capture those separately
                if not pr['author'] or pr['author']['login'] != username:
                    for review in reviews:
                        created_at = datetime.fromisoformat(review['createdAt'].replace('Z', '+00:00'))
                        if created_at >= since_datetime:
                            pr_with_review = {
                                'pr_number': pr['number'],
                                'pr_title': pr['title'],
                                'pr_url': pr['url'],
                                'pr_author': pr['author']['login'] if pr['author'] else 'Unknown',
                                'review_state': review['state'],
                                'review_body': review['body'],
                                'review_url': review['url'],
                                'created_at': review['createdAt'],
                                'review_comments': review['comments']['nodes'],
                                'review_comments_count': review['comments']['totalCount']
                            }
                            reviewed_prs.append(pr_with_review)
        
        # Check if we need to fetch more pages
        if data['repository']['pullRequests']['pageInfo']['hasNextPage']:
            cursor = data['repository']['pullRequests']['pageInfo']['endCursor']
        else:
            has_next_page = False
    
    print(f"Found {len(reviewed_prs)} PR reviews by {username}.")
    return reviewed_prs

def get_prs_with_user_comments(username, owner, name, token, since_date):
    """Fetch PRs (authored by others) where the user has commented"""
    print(f"Fetching PRs with comments by {username} in {owner}/{name} since {since_date}...")
    
    since_datetime = datetime.fromisoformat(since_date.replace('Z', '+00:00'))
    
    query = """
    query($owner: String!, $name: String!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        pullRequests(first: 100, after: $cursor, states: [OPEN, CLOSED, MERGED]) {
          pageInfo {
            endCursor
            hasNextPage
          }
          nodes {
            number
            title
            url
            createdAt
            author {
              login
            }
            comments(first: 30) {
              totalCount
              nodes {
                author {
                  login
                }
                body
                createdAt
                url
              }
            }
          }
        }
      }
    }
    """
    
    commented_prs = []
    has_next_page = True
    cursor = None
    
    while has_next_page:
        variables = {
            'owner': owner,
            'name': name,
            'cursor': cursor
        }
        
        data = make_graphql_request(query, variables, token)
        prs = data['repository']['pullRequests']['nodes']
        
        # Find PRs with comments by this user
        for pr in prs:
            # Skip PRs authored by the user
            if pr['author'] and pr['author']['login'] == username:
                continue
                
            user_comments = []
            for comment in pr['comments']['nodes']:
                if comment['author'] and comment['author']['login'] == username:
                    created_at = datetime.fromisoformat(comment['createdAt'].replace('Z', '+00:00'))
                    if created_at >= since_datetime:
                        user_comments.append(comment)
            
            if user_comments:
                commented_prs.append({
                    'pr_number': pr['number'],
                    'pr_title': pr['title'],
                    'pr_url': pr['url'],
                    'pr_author': pr['author']['login'] if pr['author'] else 'Unknown',
                    'comments': user_comments,
                    'comment_count': len(user_comments)
                })
        
        # Check if we need to fetch more pages
        if data['repository']['pullRequests']['pageInfo']['hasNextPage']:
            cursor = data['repository']['pullRequests']['pageInfo']['endCursor']
        else:
            has_next_page = False
    
    print(f"Found {len(commented_prs)} PRs with comments by {username}.")
    return commented_prs

def get_user_pr_comment_threads(username, owner, name, token, since_date):
    """Fetch comment threads on the user's own PRs"""
    print(f"Fetching comment threads on {username}'s PRs in {owner}/{name} since {since_date}...")
    
    since_datetime = datetime.fromisoformat(since_date.replace('Z', '+00:00'))
    
    query = """
    query($owner: String!, $name: String!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        pullRequests(first: 50, after: $cursor, states: [OPEN, CLOSED, MERGED]) {
          pageInfo {
            endCursor
            hasNextPage
          }
          nodes {
            number
            title
            url
            createdAt
            author {
              login
            }
            comments(first: 30) {
              totalCount
              nodes {
                author {
                  login
                }
                body
                createdAt
                url
              }
            }
          }
        }
      }
    }
    """
    
    pr_threads = []
    has_next_page = True
    cursor = None
    
    while has_next_page:
        variables = {
            'owner': owner,
            'name': name,
            'cursor': cursor
        }
        
        data = make_graphql_request(query, variables, token)
        prs = data['repository']['pullRequests']['nodes']
        
        # Process each PR
        for pr in prs:
            # Only look at PRs authored by the user
            if not pr['author'] or pr['author']['login'] != username:
                continue
                
            created_at = datetime.fromisoformat(pr['createdAt'].replace('Z', '+00:00'))
            if created_at >= since_datetime:
                # Look for comments from others on the user's PRs
                discussion_threads = []
                
                for comment in pr['comments']['nodes']:
                    # Only include comments from others (not self-comments)
                    if comment['author'] and comment['author']['login'] != username:
                        comment_created_at = datetime.fromisoformat(comment['createdAt'].replace('Z', '+00:00'))
                        if comment_created_at >= since_datetime:
                            discussion_threads.append({
                                'comment': comment,
                                'comment_author': comment['author']['login']
                            })
                
                if discussion_threads:
                    pr_threads.append({
                        'pr_number': pr['number'],
                        'pr_title': pr['title'],
                        'pr_url': pr['url'],
                        'created_at': pr['createdAt'],
                        'discussion_threads': discussion_threads,
                        'thread_count': len(discussion_threads)
                    })
        
        # Check if we need to fetch more pages
        if data['repository']['pullRequests']['pageInfo']['hasNextPage']:
            cursor = data['repository']['pullRequests']['pageInfo']['endCursor']
        else:
            has_next_page = False
    
    print(f"Found {len(pr_threads)} PRs with discussion threads involving {username}.")
    return pr_threads

def get_issue_discussions(username, owner, name, token, since_date):
    """Fetch issue discussions where the user has participated"""
    print(f"Fetching issue discussions with {username} in {owner}/{name} since {since_date}...")
    
    since_datetime = datetime.fromisoformat(since_date.replace('Z', '+00:00'))
    
    query = """
    query($owner: String!, $name: String!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        issues(first: 100, after: $cursor) {
          pageInfo {
            endCursor
            hasNextPage
          }
          nodes {
            number
            title
            url
            createdAt
            author {
              login
            }
            comments(first: 30) {
              totalCount
              nodes {
                author {
                  login
                }
                body
                createdAt
                url
              }
            }
          }
        }
      }
    }
    """
    
    discussed_issues = []
    has_next_page = True
    cursor = None
    
    while has_next_page:
        variables = {
            'owner': owner,
            'name': name,
            'cursor': cursor
        }
        
        data = make_graphql_request(query, variables, token)
        issues = data['repository']['issues']['nodes']
        
        # Find issues with comments by this user
        for issue in issues:
            user_comments = []
            
            # Add the issue itself if authored by user
            is_authored_by_user = issue['author'] and issue['author']['login'] == username
            issue_created_at = datetime.fromisoformat(issue['createdAt'].replace('Z', '+00:00'))
            
            # Check comments
            for comment in issue['comments']['nodes']:
                if comment['author'] and comment['author']['login'] == username:
                    comment_created_at = datetime.fromisoformat(comment['createdAt'].replace('Z', '+00:00'))
                    if comment_created_at >= since_datetime:
                        user_comments.append(comment)
            
            # Include if the user authored the issue or commented on it
            if (is_authored_by_user and issue_created_at >= since_datetime) or user_comments:
                discussed_issues.append({
                    'issue_number': issue['number'],
                    'issue_title': issue['title'],
                    'issue_url': issue['url'],
                    'issue_author': issue['author']['login'] if issue['author'] else 'Unknown',
                    'is_authored_by_user': is_authored_by_user,
                    'comments': user_comments,
                    'comment_count': len(user_comments)
                })
        
        # Check if we need to fetch more pages
        if data['repository']['issues']['pageInfo']['hasNextPage']:
            cursor = data['repository']['issues']['pageInfo']['endCursor']
        else:
            has_next_page = False
    
    print(f"Found {len(discussed_issues)} issues with participation by {username}.")
    return discussed_issues

def get_collaboration_stats(pr_reviews, commented_prs, pr_threads, issue_discussions):
    """Generate collaboration statistics"""
    
    # Calculate team members collaborated with
    collaborators = set()
    
    # From PR reviews
    for review in pr_reviews:
        if review['pr_author'] != 'Unknown':
            collaborators.add(review['pr_author'])
    
    # From PR comments
    for pr in commented_prs:
        if pr['pr_author'] != 'Unknown':
            collaborators.add(pr['pr_author'])
    
    # From PR threads
    for pr in pr_threads:
        for thread in pr.get('discussion_threads', []):
            if thread.get('comment_author') != 'Unknown':
                collaborators.add(thread.get('comment_author'))
    
    # From issues
    for issue in issue_discussions:
        if issue['issue_author'] != 'Unknown' and not issue['is_authored_by_user']:
            collaborators.add(issue['issue_author'])
    
    # Calculate engagement metrics
    total_review_comments = sum(review.get('review_comments_count', 0) for review in pr_reviews)
    total_pr_comments = sum(pr.get('comment_count', 0) for pr in commented_prs)
    total_thread_replies = sum(pr.get('thread_count', 0) for pr in pr_threads)
    total_issue_comments = sum(issue.get('comment_count', 0) for issue in issue_discussions)
    
    return {
        'unique_collaborators': len(collaborators),
        'collaborator_list': list(collaborators),
        'total_pr_reviews': len(pr_reviews),
        'total_review_comments': total_review_comments,
        'total_prs_commented_on': len(commented_prs),
        'total_pr_comments': total_pr_comments,
        'total_pr_discussion_threads': total_thread_replies,
        'total_issues_engaged_with': len(issue_discussions),
        'total_issue_comments': total_issue_comments,
        'total_collaboration_touchpoints': (
            len(pr_reviews) + total_review_comments + 
            total_pr_comments + total_thread_replies + 
            total_issue_comments
        )
    }

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
        
        # Get PR reviews (where user reviewed others' PRs)
        pr_reviews = get_user_pr_reviews(username, owner, name, token, since_date)
        
        # Get PRs where user commented (but didn't author)
        commented_prs = get_prs_with_user_comments(username, owner, name, token, since_date)
        
        # Get discussion threads on user's PRs
        pr_threads = get_user_pr_comment_threads(username, owner, name, token, since_date)
        
        # Get issue discussions
        issue_discussions = get_issue_discussions(username, owner, name, token, since_date)
        
        # Calculate collaboration statistics
        collaboration_stats = get_collaboration_stats(
            pr_reviews, commented_prs, pr_threads, issue_discussions
        )
        
        # Prepare the output
        result = {
            'username': username,
            'repository': repository,
            'generated_at': datetime.now().isoformat(),
            'timeframe_days': args.timeframe,
            'since_date': since_date,
            'statistics': collaboration_stats,
            'pr_reviews': pr_reviews,
            'commented_prs': commented_prs,
            'pr_discussion_threads': pr_threads,
            'issue_discussions': issue_discussions
        }
        
        # Save to file
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\nCollaboration export completed successfully to {args.output}")
        print(f"Found:")
        print(f"- {len(pr_reviews)} PR reviews")
        print(f"- {len(commented_prs)} PRs where you commented")
        print(f"- {len(pr_threads)} PRs with discussion threads")
        print(f"- {len(issue_discussions)} issues you participated in")
        print(f"- {collaboration_stats['unique_collaborators']} unique collaborators")
        print(f"- {collaboration_stats['total_collaboration_touchpoints']} total collaboration touchpoints")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()