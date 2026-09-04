package com.macro.mall.portal.observability;

import com.mongodb.event.CommandEvent;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Micrometer's Mongo metrics binder calls {@code CommandEvent#getDatabaseName}
 * while the Actuator health endpoint runs. Keep the MongoDB driver line that
 * exposes that API aligned with the Micrometer version so a packaged Portal
 * cannot become unhealthy only after its first Mongo health probe.
 */
class MongoMicrometerCompatibilityTest {

    @Test
    void mongoDriverExposesTheApiRequiredByMicrometerMongoMetrics() throws NoSuchMethodException {
        Method databaseName = CommandEvent.class.getMethod("getDatabaseName");

        assertThat(databaseName.getReturnType()).isEqualTo(String.class);
    }
}
