# ── Java backend (Spring Boot 4.0.1, Java 21, multi-module Maven) ────────────
# Build context = repo root.  Produces the single bootable app jar.
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src

# Copy the reactor poms first so dependency resolution is cached across source-only changes.
COPY pom.xml ./
COPY common/pom.xml   common/pom.xml
COPY batch/pom.xml    batch/pom.xml
COPY qc/pom.xml       qc/pom.xml
COPY user/pom.xml     user/pom.xml
COPY app/pom.xml      app/pom.xml
RUN mvn -q -B -pl app -am dependency:go-offline || true

# Now the sources, then build only the bootable module + its deps.
COPY common common
COPY batch  batch
COPY qc     qc
COPY user   user
COPY app    app
RUN mvn -q -B -DskipTests -pl app -am package

# ── Runtime ──────────────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jre
WORKDIR /app
RUN useradd -r -u 1001 spring
COPY --from=build /src/app/target/app-0.0.1-SNAPSHOT.jar app.jar
# uploads + tomcat tmp are written at runtime; make them owned by the app user.
RUN mkdir -p /app/uploads /tmp/apprisal-tomcat && chown -R spring:spring /app /tmp/apprisal-tomcat
USER spring
EXPOSE 8080 9091
ENTRYPOINT ["java","-XX:MaxRAMPercentage=75.0","-jar","app.jar"]
