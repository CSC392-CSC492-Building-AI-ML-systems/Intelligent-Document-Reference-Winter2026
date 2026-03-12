package com.acme.platform.core.application.services;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import static org.junit.jupiter.api.Assertions.*;

class SearchServiceTest {
    private SearchService subject;

    @BeforeEach
    void setUp() {
        subject = new SearchService();
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
