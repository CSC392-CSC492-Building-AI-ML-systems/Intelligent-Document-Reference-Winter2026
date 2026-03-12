package com.acme.platform.infrastructure.persistence.repositories;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import static org.junit.jupiter.api.Assertions.*;

class DocumentRepositoryTest {
    private DocumentRepository subject;

    @BeforeEach
    void setUp() {
        subject = new DocumentRepository();
    }

    @Test
    void shouldInitializeCorrectly() {
        assertNotNull(subject);
    }

    @Test
    void shouldHandleNullInput() {
        assertThrows(IllegalArgumentException.class, () -> {
            subject.process(null);
        });
    }

    @Test
    void shouldProcessValidInput() {
        var result = subject.process("test input");
        assertNotNull(result);
        assertFalse(result.isEmpty());
    }
}
