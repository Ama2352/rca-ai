export interface ScenarioOverview {
  title: string
  description: string
  cause: string
  affectedServices: string[]
  observations: string[]
  investigation: string
}

export const scenarioOverviews: Record<string, ScenarioOverview> = {
  "missing-secret-01": {
    title: "Telemetry Docs Startup Failure",
    description: "A Kubernetes container cannot start because its configuration is incomplete.",
    cause: "The deployment refers to a Kubernetes Secret that does not exist.",
    affectedServices: ["telemetry-docs"],
    observations: [
      "A replacement pod cannot start.",
      "Kubernetes reports a container configuration error because the Secret is missing.",
    ],
    investigation: "Examine the pod state, container configuration, and Kubernetes events.",
  },
  "application-failure-01": {
    title: "Checkout and Payment Failure",
    description: "Customers encounter errors while placing orders and processing payments.",
    cause: "The Payment Failure fault-injection scenario was enabled, causing some Payment charges to fail.",
    affectedServices: ["checkout", "payment"],
    observations: [
      "Checkout PlaceOrder operations report errors.",
      "Payment Charge operations report errors.",
      "Payment warning logs appear alongside the errors.",
    ],
    investigation: "Determine how the observed Payment errors relate to Checkout failures.",
  },
  "ad-high-cpu-01": {
    title: "Ad Service High CPU",
    description: "The Ad service experiences a sudden increase in CPU usage.",
    cause: "The Ad High CPU fault-injection scenario was enabled.",
    affectedServices: ["ad"],
    observations: [
      "CPU usage rises sharply in the Ad service.",
      "Logs and traces may provide additional context about the change.",
    ],
    investigation: "Determine what explains the CPU spike and whether the evidence establishes its cause.",
  },
  "cart-failure-01": {
    title: "Cart Failure",
    description: "Some cart-clearing operations fail while the Cart service remains running.",
    cause: "The Cart Failure scenario injects failures into the Cart storage path.",
    affectedServices: ["checkout", "cart"],
    observations: [
      "Cart reports storage connection errors during EmptyCart operations.",
      "Some EmptyCart operations fail.",
      "Other Cart-to-Valkey activity still succeeds.",
    ],
    investigation: "Trace the failed Checkout-to-Cart operation and its storage dependency.",
  },
  "dependency-unavailable-01": {
    title: "Payment Dependency Unavailable",
    description: "Checkout cannot reliably reach the Payment service.",
    cause: "The Payment Unreachable scenario directs relevant requests to an invalid endpoint.",
    affectedServices: ["checkout", "payment"],
    observations: [
      "Payment Charge requests from Checkout return UNAVAILABLE.",
      "Related Checkout operations also fail.",
    ],
    investigation: "Examine the failed service dependency and how it affects Checkout.",
  },
  "downstream-latency-01": {
    title: "Shipping Slowdown",
    description: "Some shipping operations take longer, slowing the services that call them.",
    cause: "The International Shipping Slowdown scenario delays qualifying international shipments.",
    affectedServices: ["checkout", "shipping"],
    observations: [
      "Ship-order latency increases.",
      "Checkout-to-Shipping latency also increases.",
      "Get-quote latency stays near its usual level.",
    ],
    investigation: "Find which shipping path is slow and whether it explains the delay seen by its caller.",
  },
  "memory-leak-01": {
    title: "Email Service Memory Growth",
    description: "The Email service uses more memory and takes longer to complete email operations.",
    cause: "The Email Memory Leak simulation adds memory pressure by using larger email payloads.",
    affectedServices: ["email"],
    observations: [
      "Email service memory usage grows while available memory decreases.",
      "Send-email latency rises, with no operation errors recorded.",
    ],
    investigation: "Examine memory growth and how it relates to email latency.",
  },
  "messaging-failure-01": {
    title: "Messaging Slowdown",
    description: "Order messages move more slowly between Checkout and downstream consumers.",
    cause: "The Kafka queue-problem simulation introduces a delay in consumer-side processing.",
    affectedServices: ["checkout", "fraud-detection", "kafka"],
    observations: [
      "Fraud Detection's last-poll age increases.",
      "Publishing orders takes longer.",
      "Measured consumer lag remains at zero.",
    ],
    investigation: "Examine producer and consumer behavior without assuming consumer lag increased.",
  },
  "crash-loop-backoff-01": {
    title: "Container Restart Loop",
    description: "A Kubernetes container repeatedly stops and restarts instead of becoming ready.",
    cause: "The demo changes the container command so the process exits with code 42.",
    affectedServices: ["telemetry-docs"],
    observations: [
      "The container repeatedly terminates.",
      "Kubernetes reports BackOff events.",
      "The container is not ready.",
    ],
    investigation: "Explain the restart behavior using the available Kubernetes evidence.",
  },
}
