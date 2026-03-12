def test_registry_importable():
    import model_clients.registry as registry

    assert hasattr(registry, "ClientRegistry")
