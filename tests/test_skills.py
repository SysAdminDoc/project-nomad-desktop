"""Tests for skills API routes."""


class TestSkillsList:
    def test_list_skills(self, client):
        resp = client.get('/api/skills')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


class TestSkillsCreate:
    def test_create_skill(self, client):
        resp = client.post('/api/skills', json={
            'name': 'Fire Starting',
            'category': 'Fire',
            'proficiency': 'intermediate',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'Fire Starting'
        assert data['category'] == 'Fire'
        assert data['id'] is not None

    def test_create_skill_requires_name(self, client):
        resp = client.post('/api/skills', json={'category': 'Fire'})
        assert resp.status_code == 400

    def test_create_skill_empty_name_rejected(self, client):
        resp = client.post('/api/skills', json={'name': '  ', 'category': 'Fire'})
        assert resp.status_code == 400


class TestSkillsUpdate:
    def test_update_skill(self, client):
        create = client.post('/api/skills', json={
            'name': 'Knot Tying',
            'proficiency': 'none',
        })
        sid = create.get_json()['id']
        resp = client.put(f'/api/skills/{sid}', json={
            'name': 'Knot Tying',
            'proficiency': 'advanced',
        })
        assert resp.status_code == 200
        assert resp.get_json()['proficiency'] == 'advanced'


class TestSkillsDelete:
    def test_delete_skill(self, client):
        create = client.post('/api/skills', json={'name': 'Temp Skill'})
        sid = create.get_json()['id']
        resp = client.delete(f'/api/skills/{sid}')
        assert resp.status_code == 200


class TestSkillsSeed:
    def test_seed_defaults(self, client):
        # Clear skills first
        resp = client.post('/api/skills/seed-defaults')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'seeded' in data
