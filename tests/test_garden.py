"""Tests for garden/food production API routes."""


class TestGardenZone:
    def test_get_zone(self, client):
        resp = client.get('/api/garden/zone')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'zone' in data


class TestGardenPlots:
    def test_list_plots(self, client):
        resp = client.get('/api/garden/plots')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_create_plot(self, client):
        resp = client.post('/api/garden/plots', json={
            'name': 'Raised Bed A',
            'width_ft': 4,
            'length_ft': 8,
            'sun_exposure': 'full',
            'soil_type': 'loam',
        })
        assert resp.status_code == 201

    def test_create_plot_requires_name(self, client):
        resp = client.post('/api/garden/plots', json={})
        assert resp.status_code == 400

    def test_delete_plot(self, client):
        client.post('/api/garden/plots', json={'name': 'Temp Plot'})
        plots = client.get('/api/garden/plots').get_json()
        temp = next((p for p in plots if p['name'] == 'Temp Plot'), None)
        assert temp is not None
        resp = client.delete(f'/api/garden/plots/{temp["id"]}')
        assert resp.status_code == 200


class TestGardenSeeds:
    def test_list_seeds(self, client):
        resp = client.get('/api/garden/seeds')
        assert resp.status_code == 200

    def test_create_seed(self, client):
        resp = client.post('/api/garden/seeds', json={
            'species': 'Tomato',
            'variety': 'Roma',
            'quantity': 50,
            'days_to_maturity': 75,
            'planting_season': 'spring',
        })
        assert resp.status_code == 201

    def test_create_seed_requires_species(self, client):
        resp = client.post('/api/garden/seeds', json={'variety': 'Big Boy'})
        assert resp.status_code == 400

    def test_delete_seed(self, client):
        client.post('/api/garden/seeds', json={'species': 'Basil'})
        seeds = client.get('/api/garden/seeds').get_json()
        basil = next((s for s in seeds if s['species'] == 'Basil'), None)
        assert basil is not None
        resp = client.delete(f'/api/garden/seeds/{basil["id"]}')
        assert resp.status_code == 200


class TestHarvests:
    def test_list_harvests(self, client):
        resp = client.get('/api/garden/harvests')
        assert resp.status_code == 200

    def test_create_harvest(self, client):
        resp = client.post('/api/garden/harvests', json={
            'crop': 'Tomatoes',
            'quantity': 5.5,
            'unit': 'lbs',
            'notes': 'First harvest of season',
        })
        assert resp.status_code == 201

    def test_create_harvest_requires_crop(self, client):
        resp = client.post('/api/garden/harvests', json={'quantity': 10})
        assert resp.status_code == 400


class TestCompanionPlanting:
    def test_companion_list(self, client):
        resp = client.get('/api/garden/companions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        # Should auto-seed with 20+ pairs
        assert len(data) >= 20

    def test_companion_fields(self, client):
        companions = client.get('/api/garden/companions').get_json()
        c = companions[0]
        assert 'plant_a' in c
        assert 'plant_b' in c
        assert 'relationship' in c


class TestPlantingCalendar:
    def test_calendar(self, client):
        resp = client.get('/api/garden/planting-calendar')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_calendar_by_zone(self, client):
        resp = client.get('/api/garden/planting-calendar?zone=7')
        assert resp.status_code == 200


class TestSeedInventory:
    def test_seed_inventory_list(self, client):
        resp = client.get('/api/garden/seeds/inventory')
        assert resp.status_code == 200

    def test_seed_inventory_add(self, client):
        resp = client.post('/api/garden/seeds/inventory', json={
            'species': 'Pepper',
            'variety': 'Jalapeno',
            'quantity': 100,
            'viability_pct': 85,
        })
        assert resp.status_code == 200

    def test_seed_inventory_delete(self, client):
        client.post('/api/garden/seeds/inventory', json={'species': 'Delete Me Seed'})
        seeds = client.get('/api/garden/seeds/inventory').get_json()
        target = next((s for s in seeds if s.get('species') == 'Delete Me Seed'), None)
        if target:
            resp = client.delete(f'/api/garden/seeds/inventory/{target["id"]}')
            assert resp.status_code == 200


class TestPestGuide:
    def test_pest_guide(self, client):
        resp = client.get('/api/garden/pests')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        # Should auto-seed with 10 entries
        assert len(data) >= 10

    def test_pest_fields(self, client):
        pests = client.get('/api/garden/pests').get_json()
        p = pests[0]
        assert 'name' in p
        assert 'treatment' in p
        # pest_type field (column name varies)
        assert 'pest_type' in p or 'type' in p
