FROM maven:3.9.9-eclipse-temurin-8 AS build

WORKDIR /workspace
# Copy the Maven model first.  This layer changes only when a dependency or
# plugin declaration changes, so ordinary Java edits reuse the downloaded
# dependency cache on later Docker builds.
COPY pom.xml ./
COPY mall-common/pom.xml mall-common/pom.xml
COPY mall-mbg/pom.xml mall-mbg/pom.xml
COPY mall-security/pom.xml mall-security/pom.xml
COPY mall-demo/pom.xml mall-demo/pom.xml
COPY mall-admin/pom.xml mall-admin/pom.xml
COPY mall-search/pom.xml mall-search/pom.xml
COPY mall-portal/pom.xml mall-portal/pom.xml
RUN mvn -B -pl mall-portal -am dependency:go-offline -DskipTests -Ddocker.skip=true

# Only the modules required by mall-portal need to be compiled for this image.
COPY mall-common/src mall-common/src
COPY mall-mbg/src mall-mbg/src
COPY mall-security/src mall-security/src
COPY mall-portal/src mall-portal/src
RUN mvn -B -pl mall-portal -am package -DskipTests -Ddocker.skip=true

FROM eclipse-temurin:8-jre-jammy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /workspace/mall-portal/target/mall-portal-1.0-SNAPSHOT.jar /app/app.jar

EXPOSE 8085

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
