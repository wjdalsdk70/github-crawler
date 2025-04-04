from fastapi import FastAPI, HTTPException, Query, Header
from typing import Optional
from datetime import datetime
import requests

app = FastAPI()

@app.get("/get_commits")
async def get_commits_raw(
    owner: str,
    repo: str,
    branch: Optional[str] = Query(None, description="브랜치 이름 (예: main, dev 등)"),
    since: Optional[str] = Query(None, description="시작 날짜 (ISO 8601 형식)"),
    until: Optional[str] = Query(None, description="종료 날짜 (ISO 8601 형식)"),
    token: str = Header(...)
):
    """
    특정 브랜치의 커밋 정보를 전체 JSON으로 반환하는 API
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    params = {}
    if branch:
        params['sha'] = branch
    if since:
        params['since'] = since
    if until:
        params['until'] = until

    response = requests.get(f"https://api.github.com/repos/{owner}/{repo}/commits", headers=headers, params=params)

    if response.status_code == 200:
        return response.json()  # ✅ 전체 커밋 데이터 그대로 반환
    else:
        raise HTTPException(status_code=response.status_code, detail=response.json())

@app.get("/get_commits_with_diff")
async def get_commits_with_diff(
    owner: str,
    repo: str,
    branch: Optional[str] = Query(None, description="브랜치 이름 (예: main, dev 등)"),
    since: Optional[str] = Query(None, description="시작 날짜 (ISO 8601 형식)"),
    until: Optional[str] = Query(None, description="종료 날짜 (ISO 8601 형식)"),
    token: str = Header(...)
):
    """
    커밋의 변경된 파일(diff) 정보까지 포함하여 반환하는 API
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    params = {}
    if branch:
        params['sha'] = branch
    if since:
        params['since'] = since
    if until:
        params['until'] = until

    # 전체 커밋 목록 요청
    commits_res = requests.get(f"https://api.github.com/repos/{owner}/{repo}/commits", headers=headers, params=params)

    if commits_res.status_code != 200:
        raise HTTPException(status_code=commits_res.status_code, detail=commits_res.json())

    commits = commits_res.json()
    result = []

    for commit in commits:
        sha = commit.get("sha")
        if not sha:
            continue
        
        # 각 커밋의 상세 정보 요청
        detail_res = requests.get(f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}", headers=headers)
        if detail_res.status_code != 200:
            continue  # 실패한 커밋은 생략

        detail = detail_res.json()
        result.append({
            "sha": sha,
            "commit": commit.get("commit"),
            "author": commit.get("author"),
            "files": detail.get("files", [])  # 변경된 파일 정보 (patch 포함)
        })

    return result

@app.get("/get_commit_messages_and_changes")
async def get_commit_messages_and_changes(
    owner: str,
    repo: str,
    branch: Optional[str] = Query(None, description="브랜치 이름 (예: main, dev 등)"),
    since: Optional[datetime] = Query(None, description="시작 날짜 (ISO 8601 형식)"),
    until: Optional[datetime] = Query(None, description="종료 날짜 (ISO 8601 형식)"),
    token: str = Header(...)
):
    """
    각 커밋의 메시지와 변경된 코드(patch)만 반환하는 API
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    params = {}
    if branch:
        params['sha'] = branch
    if since:
        params['since'] = since.isoformat()
    if until:
        params['until'] = until.isoformat()

    commits_res = requests.get(f"https://api.github.com/repos/{owner}/{repo}/commits", headers=headers, params=params)

    if commits_res.status_code != 200:
        raise HTTPException(status_code=commits_res.status_code, detail=commits_res.json())

    commits = commits_res.json()
    result = []

    for commit in commits:
        sha = commit.get("sha")
        if not sha:
            continue

        detail_res = requests.get(f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}", headers=headers)
        if detail_res.status_code != 200:
            continue

        detail = detail_res.json()

        message = detail.get("commit", {}).get("message", "")
        patches = []

        for file in detail.get("files", []):
            patch = file.get("patch")
            filename = file.get("filename")
            if patch:
                patches.append({
                    "filename": filename,
                    "patch": patch
                })

        result.append({
            "message": message,
            "changes": patches
        })

    return result

@app.get("/get_repo_project_todo_items")
async def get_repo_project_todo_items(
    owner: str = Query(..., description="GitHub 레포 소유자 (user or org)"),
    repo: str = Query(..., description="레포 이름"),
    project_title_filter: Optional[str] = Query(None, description="특정 프로젝트 제목 필터링"),
    token: str = Header(...)
):
    """
    특정 GitHub 레포의 Project v2 중, 'Status'가 'Todo'인 항목들만 반환
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }

    # Step 1: 레포의 프로젝트 목록 조회 (GraphQL)
    project_query = f"""
    query {{
      repository(owner: "{owner}", name: "{repo}") {{
        projectsV2(first: 10) {{
          nodes {{
            id
            title
          }}
        }}
      }}
    }}
    """

    project_res = requests.post("https://api.github.com/graphql", json={"query": project_query}, headers=headers)
    if project_res.status_code != 200:
        raise HTTPException(status_code=project_res.status_code, detail=project_res.json())

    project_nodes = project_res.json().get("data", {}).get("repository", {}).get("projectsV2", {}).get("nodes", [])

    if not project_nodes:
        raise HTTPException(status_code=404, detail="해당 레포에 연결된 Project v2가 없습니다.")

    # Step 2: 필터링 조건 적용
    selected_project = None
    if project_title_filter:
        for p in project_nodes:
            if project_title_filter.lower() in p["title"].lower():
                selected_project = p
                break
        if not selected_project:
            raise HTTPException(status_code=404, detail=f"'{project_title_filter}'에 해당하는 프로젝트를 찾을 수 없습니다.")
    else:
        selected_project = project_nodes[0]  # 첫 번째 프로젝트 사용

    project_id = selected_project["id"]

    # Step 3: 해당 프로젝트의 항목들 중 Status = Todo 필터링
    item_query = f"""
    query {{
      node(id: "{project_id}") {{
        ... on ProjectV2 {{
          title
          items(first: 100) {{
            nodes {{
              id
              content {{
                ... on Issue {{
                  title
                  number
                  state
                  url
                }}
                ... on PullRequest {{
                  title
                  number
                  state
                  url
                }}
              }}
              fieldValues(first: 20) {{
                nodes {{
                  ... on ProjectV2ItemFieldSingleSelectValue {{
                    field {{
                      ... on ProjectV2SingleSelectField {{
                        name
                      }}
                    }}
                    name
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """

    item_res = requests.post("https://api.github.com/graphql", json={"query": item_query}, headers=headers)
    if item_res.status_code != 200:
        raise HTTPException(status_code=item_res.status_code, detail=item_res.json())

    project_data = item_res.json().get("data", {}).get("node", {})
    items = project_data.get("items", {}).get("nodes", [])

    todo_items = []
    for item in items:
        status = None
        for field in item.get("fieldValues", {}).get("nodes", []):
            if field.get("field", {}).get("name", "").lower() == "status":
                status = field.get("name")
                break

        if status == "Todo":
            content = item.get("content", {})
            todo_items.append({
                "id": item.get("id"),
                "title": content.get("title"),
                "number": content.get("number"),
                "state": content.get("state"),
                "url": content.get("url")
            })

    return {
        "project_title": project_data.get("title"),
        "todo_items": todo_items
    }
