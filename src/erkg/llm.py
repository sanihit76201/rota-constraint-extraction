"""Budget-enforcing client for the provided endpoint.
* every call carries `X-Item-Id`
* model, temperature=1.0, top_p=0.95, reasoning disabled -- fixed
* hard per-item cap on calls: failed attempts and retries count too
"""
import os


class BudgetExceeded(RuntimeError):
    pass


def load_env(root):
    for path in (os.path.join(root, ".env"), os.path.join(root, "candidate_package", ".env")):
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Endpoint:
    def __init__(self):
        from openai import OpenAI
        self.model = os.environ.get("MODEL", "ibm-granite/granite-4.2-8b")
        self.client = OpenAI(base_url=os.environ["OPENROUTER_BASE_URL"],
                             api_key=os.environ["OPENROUTER_API_KEY"],
                             max_retries=0, timeout=120)   # SDK retries would be uncounted calls

    def chat(self, item_id, system, user, max_tokens=3000):
        r = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=1.0, top_p=0.95, max_tokens=max_tokens,
            extra_headers={"X-Item-Id": item_id},
            extra_body={"reasoning": {"enabled": False}},
        )
        return r.choices[0].message.content or ""


class ItemClient:
    """Wraps an endpoint (or a test double with .chat) with a per-item call cap."""

    def __init__(self, endpoint, item_id, cap):
        self.endpoint, self.item_id, self.cap, self.used = endpoint, item_id, cap, 0

    def chat(self, system, user, **kw):
        if self.used >= self.cap:
            raise BudgetExceeded(self.item_id)
        self.used += 1                      # counted before the attempt: a failure is still a call
        return self.endpoint.chat(self.item_id, system, user, **kw)