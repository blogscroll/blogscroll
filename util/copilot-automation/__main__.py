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
            "Use this file as a general reference for TOML format that I want you to use: web/data/categories/technology/list.toml in the blogscroll/blogscroll repository. DO NOT USE THIS CONTENT IN THE RESPONSE. "
            "If your response includes ANY content from this file, it will be considered incorrect. "
            "From the current issue body, generate a TOML blob that can be inserted into the file defined as the category property. "
            "If the generated TOML does not represent the CURRENT ISSUE BODY, it will be considered incorrect. "
            "The result ID (in square brackets) should always be in the form [blog.] where what follows after the period is the site domain part from the Site URL section without the protocol, and the periods are omitted entirely. "
            "Just in the TOML header (between square brackets) that represents the site there could be only alphanumeric characters. No hyphens, underscores, or any other special characters. "
            "The [blog.] part should be in lowercase and ALWAYS there. The period separating it from the rest should ALWAYS be there. "
            "The domain part after 'blog.' should be in lowercase and always there. Make sure to letters are missing, even if they are duplicated. "
            "Include the file path where the blob needs to be inserted. The file path is of the pattern web/data/categories/REPLACE-CATEGORY-HERE/list.toml. "
            "The REPLACE-CATEGORY-HERE should match 1:1 the category that is provided in the issue body, in the Site category section."
            "The TOML content should NOT contain any properties other than name, url, and favicon. If other properties are present, the results will be considered incorrect. "
            "Return data in JSON format (just the JSON). JSON response should have two properties - `content` for the TOML content, and `file_path` for the file path."
            "UNDER NO CIRCUMSTANCES in the response you produce should you include Markdown markers (```) that delineate the code fragment."
            "Just return the raw JSON without the triple ticks. If your response contains ```, it will be considered incorrect."
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


def fetch_thread_responses(api_token, prompt, conversation_url):
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

def delete_thread(api_token, conversation_url):
    """Send a conversation prompt and stream responses."""
    headers = {
        "Authorization": f"GitHub-Bearer {api_token}",
    }
    response = requests.delete(conversation_url, headers=headers)
    if response.status_code not in [200, 201, 204]:
        raise Exception(f"Failed to delete thread. Status code: {response.status_code}, Response: {response.text}")
    
    return True

def main():
    args = get_args()
    session_id = args.session_id
    issue_id = args.issue_id
    issue_number = args.issue_number

    # Endpoints
    token_endpoint = "https://github.com/github-copilot/chat/token"
    thread_bootstrap_url = "https://api.individual.githubcopilot.com/github/chat/threads"

    # Fetch API token
    #print("Fetching API token...")
    api_token = fetch_api_token(session_id, token_endpoint)

    # Bootstrap a thread
    #print("Bootstrapping thread...")
    thread_state = bootstrap_thread(api_token, thread_bootstrap_url)
    thread_id = thread_state['thread_id']
    #print(f"Thread ID: {thread_id}")

    # Build and send conversation prompt
    json_prompt = build_json_prompt(issue_id=issue_id, issue_number=issue_number)
    thread_conversation_url = f"https://api.individual.githubcopilot.com/github/chat/threads/{thread_id}/messages"
    #print(f"Sending conversation prompt to thread {thread_id}...")
    response_content = fetch_thread_responses(api_token, json_prompt, thread_conversation_url)

    # Print the final response
    #print("Response from thread:")

    print(response_content)

    thread_conversation_url = f"https://api.individual.githubcopilot.com/github/chat/threads/{thread_id}"
    #print(f'{thread_conversation_url} deleting...')
    thread_deleted = delete_thread(api_token, thread_conversation_url)


if __name__ == "__main__":
    main()
