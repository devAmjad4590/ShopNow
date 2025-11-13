# ShopNow - Spring Boot Microservices Demo

This project demonstrates a scalable e-commerce backend using Java, Spring Boot, and Docker Compose. It features a choreography-based Saga pattern, event-driven architecture with Kafka, and essential production patterns.

## Project Structure

- `services/` – Each subfolder is a microservice (auth, user, product, cart, order, inventory, payment, notification, api-gateway)
- `shared/` – Shared models and common code, e.g., event payloads, DTOs
- `docs/` – Architecture diagrams, API descriptions, Saga flow docs, and setup notes
- `docker-compose.yml` – Local orchestration: Kafka (KRaft mode), PostgreSQL, Redis, and placeholders for all services

## Core Technologies

- Java 17+, Spring Boot 3.x
- Spring Web, Data JPA, Security, and Cloud Gateway
- Apache Kafka (no Zookeeper, KRaft mode)
- PostgreSQL
- Redis (for cart)
- Docker Compose

## Key Design Patterns

- **Choreography-based Saga** via Kafka events (order-events, inventory-events, payment-events)
- **Event-driven Communication:** Microservices emit/consume events instead of direct HTTP calls
- **Resilience:** Circuit breaker with Resilience4j (to be added as services are built)
- **Separation:** Each service is responsible for a domain; shared models and contracts are versioned in `/shared`

## Getting Started

### Prerequisites

- Java 17+
- Docker + Docker Compose
- Maven

### Running Infrastructure
```
docker-compose up -d
```

This starts Kafka (KRaft mode), PostgreSQL, and Redis. Add services to the compose file as you implement them.

### Next Steps

1. Scaffold the `auth-service` (user registration, login, JWT)
2. Add user, product, order, inventory, payment, cart, and notification services one-by-one
3. Connect services with Kafka topics for events and sagas
4. Expand the documentation in `/docs` as you add logic

## Documentation Plan

- **/docs/architecture.md**: System diagrams and component overview
- **/docs/saga-flow.md**: Step-by-step Saga explanation (happy and failure paths)
- **/docs/api-documentation.md**: REST endpoint contracts per service

## Contribution

Open for learning, feedback, and improvements. Contributions welcome as this becomes a portfolio-quality example.

---

> This project is for educational demonstration. For real-world readiness, add authentication, logging, monitoring, testing, and observability as described in the documentation.
