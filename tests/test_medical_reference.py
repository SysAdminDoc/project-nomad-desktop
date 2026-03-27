"""Tests for expanded medical reference database and search."""


class TestMedicalReference:
    def test_get_all_references(self, client):
        resp = client.get('/api/medical/reference')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'categories' in data
        assert 'data' in data
        # Should have at least 10 categories (5 original + 7 new)
        assert len(data['categories']) >= 10

    def test_original_categories_present(self, client):
        resp = client.get('/api/medical/reference')
        cats = resp.get_json()['categories']
        for cat in ['vital_signs', 'drug_dosages', 'triage', 'burns', 'bleeding']:
            assert cat in cats

    def test_new_categories_present(self, client):
        resp = client.get('/api/medical/reference')
        cats = resp.get_json()['categories']
        for cat in ['fractures', 'poisoning', 'environmental', 'allergic', 'cardiac', 'respiratory', 'dental', 'wound_closure', 'pediatric', 'eye_injuries']:
            assert cat in cats

    def test_get_single_category(self, client):
        resp = client.get('/api/medical/reference?category=fractures')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['title'] == 'Fracture Management'
        assert len(data['items']) >= 5

    def test_get_pediatric(self, client):
        resp = client.get('/api/medical/reference?category=pediatric')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'Pediatric' in data['title']

    def test_get_environmental(self, client):
        resp = client.get('/api/medical/reference?category=environmental')
        assert resp.status_code == 200
        items = resp.get_json()['items']
        conditions = [i['condition'] for i in items]
        assert any('Hypothermia' in c for c in conditions)
        assert any('Heat Stroke' in c for c in conditions)


class TestMedicalReferenceSearch:
    def test_search_empty_query(self, client):
        resp = client.get('/api/medical/reference/search?q=')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_search_finds_results(self, client):
        resp = client.get('/api/medical/reference/search?q=tourniquet')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1
        assert all('category' in r for r in data)
        assert all('item' in r for r in data)

    def test_search_across_categories(self, client):
        resp = client.get('/api/medical/reference/search?q=epinephrine')
        data = resp.get_json()
        assert len(data) >= 1

    def test_search_case_insensitive(self, client):
        r1 = client.get('/api/medical/reference/search?q=CPR').get_json()
        r2 = client.get('/api/medical/reference/search?q=cpr').get_json()
        assert len(r1) == len(r2)

    def test_search_no_results(self, client):
        resp = client.get('/api/medical/reference/search?q=xyznonexistent123')
        assert resp.status_code == 200
        assert resp.get_json() == []
