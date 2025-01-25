import requests
import sseclient
import json
import argparse

def get_args():
    """Parse and return command-line arguments."""
    parser = argparse.ArgumentParser(description="Automate BlogScroll entry identification with GitHub Copilot.")
    parser.add_argument("--session-id", required=True, help="The session ID to use.")
    parser.add_argument("--issue-id", required=True, help="Issue ID (not number) for which context extraction is happening.")
    parser.add_argument("--issue-number", required=True, help="Issue number for which context extraction is happening.")
    return parser.parse_args()

def fetch_api_token(session_id, token_url):
    """Fetch the API token using the provided session ID."""
    headers = {
        'Cookie': session_id,
        'X-Requested-With': 'XMLHttpRequest',
        'GitHub-Verified-Fetch': 'true',
        'Origin': 'https://github.com'
    }
    response = requests.post(token_url, headers=headers)
    if response.status_code not in [200, 201]:
        raise Exception(f"Failed to fetch API token. Status code: {response.status_code}, Response: {response.text}")
    return response.json().get('token')

def bootstrap_thread(api_token, bootstrap_url):
    """Initialize a conversation thread and return the thread state."""
    headers = {
        "Authorization": f"GitHub-Bearer {api_token}",
        "Content-Type": "application/json"
    }
    response = requests.post(bootstrap_url, headers=headers)
    if response.status_code not in [200, 201]:
        raise Exception(f"Failed to bootstrap thread. Status code: {response.status_code}, Response: {response.text}")
    return response.json()

def build_json_prompt(issue_number, issue_id):
    """Build the JSON prompt for the thread conversation."""
    return json.dumps({
        "content": (
            "Use this file as a general reference for TOML format: web/data/categories/technology/list.toml in the blogscroll/blogscroll repository. DO NOT USE THIS CONTENT IN THE RESPONSE. "
            "The ID (in square brackets) should always be in the form [blog.] where what follows after the period is the site domain part from the Site URL section without the protocol, and the periods are omitted entirely. "
            "In the TOML header section that represents the site there could be only alphanumeric characters. No hyphens, underscores, or any other special characters. "
            "Based on the current issue in the current repository that you have in the context, generate a TOML blob that can be inserted into the file defined as the category property. "
            "Include the file path where the blob needs to be inserted. The file path is of the pattern web/data/categories/{category}/list.toml. "
            "Return data in JSON format (just the JSON). JSON response should have two properties - `content` for the TOML content, and `file_path` for the file path."
            "DO NOT include Markdown markers in your response that delineate the code fragment - just the raw JSON without the triple ticks."
        ),
        "intent": "conversation",
        "context": [
        {
            "type": "issue",
            "id": int(issue_id),
            "number": int(issue_number),
            "repository": {
                "id": 314958631,
                "name": "blogscroll",
                "owner": "blogscroll"
            }
        }
        ],
        "currentURL": f"https://github.com/blogscroll/blogscroll/issues/{issue_number}",
        "streaming": True,
        "confirmations": [],
        "customInstructions": [],
        "mode": "assistive",
        "parentMessageID": "",
        "tools": []
    })


def fetch_thread_responses(api_token, thread_id, prompt, conversation_url):
    """Send a conversation prompt and stream responses."""
    headers = {
        "Authorization": f"GitHub-Bearer {api_token}",
        "Content-Type": "application/json"
    }
    response = requests.post(conversation_url, headers=headers, stream=True, data=prompt)
    if response.status_code not in [200, 201]:
        raise Exception(f"Failed to send prompt. Status code: {response.status_code}, Response: {response.text}")
    
    client = sseclient.SSEClient(response)
    response_content = ''
    for event in client.events():
        data = json.loads(event.data)
        if data.get('type') == 'content':
            response_content += data['body']
    return response_content


def main():
    args = get_args()
    session_id = args.session_id
    issue_id = args.issue_id
    issue_number = args.issue_number

    # Endpoints
    token_endpoint = "https://github.com/github-copilot/chat/token"
    thread_bootstrap_url = "https://api.individual.githubcopilot.com/github/chat/threads"

    # Fetch API token
    print("Fetching API token...")
    api_token = fetch_api_token(session_id, token_endpoint)

    # Bootstrap a thread
    print("Bootstrapping thread...")
    thread_state = bootstrap_thread(api_token, thread_bootstrap_url)
    thread_id = thread_state['thread_id']
    print(f"Thread ID: {thread_id}")

    # Build and send conversation prompt
    json_prompt = build_json_prompt(issue_id=issue_id, issue_number=issue_number)
    thread_conversation_url = f"https://api.individual.githubcopilot.com/github/chat/threads/{thread_id}/messages"
    print(f"Sending conversation prompt to thread {thread_id}...")
    response_content = fetch_thread_responses(api_token, thread_id, json_prompt, thread_conversation_url)

    # Print the final response
    print("Response from thread:")
    print(response_content)


if __name__ == "__main__":
    main()
