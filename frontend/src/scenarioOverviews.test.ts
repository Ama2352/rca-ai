import { expect, test } from "vitest"
import { scenarioOverviews } from "./scenarioOverviews"

const finalized = {
  "missing-secret-01": {
    title: "Telemetry Docs Startup Failure",
    description: "A new Telemetry Docs container cannot start because Kubernetes cannot find a Secret required by its configuration.",
    cause: "The `telemetry-docs` deployment references a Kubernetes Secret named `eda-capture-secret-does-not-exist`, but that Secret is missing from the cluster. Kubernetes therefore cannot complete the affected container's startup configuration.",
    observations: [
      "The new Telemetry Docs Pod remains Pending, and its container is not ready.",
      "Kubernetes reports `CreateContainerConfigError` while attempting to start the container.",
      "Kubernetes repeatedly records a Failed event stating that the required Secret cannot be found.",
      "A separate, existing Telemetry Docs Pod remains running and ready, so the entire deployment is not necessarily unavailable.",
    ],
    investigation: "Determine whether the missing Secret explains why the new container cannot start, using the Pod state and Kubernetes events.",
  },
  "application-failure-01": {
    title: "Checkout and Payment Failure",
    description: "Customers encounter errors when placing orders because payment requests are failing.",
    cause: "The Payment service rejects charge requests because payment token validation fails. These failed payment operations cause related Checkout order requests to fail.",
    observations: [
      "Checkout begins reporting `INTERNAL` errors for its `PlaceOrder` operation.",
      "Traces show that both Checkout's `PlaceOrder` requests and Payment's `Charge` requests fail during the incident.",
      "Payment warning logs report invalid payment tokens. This warning pattern appears six times during the incident window and does not appear in the baseline window.",
      "Successful payment completion messages disappear during the incident, even though the Checkout and Payment containers remain running.",
    ],
    investigation: "Determine how the payment token errors relate to failed Charge requests and the resulting Checkout order failures.",
  },
  "ad-high-cpu-01": {
    title: "Ad Service High CPU",
    description: "The Ad service experiences a sharp increase in CPU usage while continuing to handle requests.",
    cause: "CPU-intensive processing in the Ad service increases the amount of CPU consumed by its Pod.",
    observations: [
      "The Ad service's reported CPU usage rises sharply compared with its baseline level.",
      "An informational log pattern referring to high CPU load becomes more frequent during the incident.",
      "The Ad service continues running and remains ready while CPU consumption is elevated.",
      "The selected traces do not show a corresponding increase in Ad request latency or request errors.",
    ],
    investigation: "Identify the evidence associated with the CPU spike and determine how strongly it supports an explanation for the increased workload.",
  },
  "cart-failure-01": {
    title: "Cart Storage Connection Failure",
    description: "Some cart-clearing requests fail while the Cart service itself remains available.",
    cause: "The Cart service encounters connection failures while communicating with its Redis-compatible Valkey storage backend. The failure affects cart-clearing operations without stopping the entire Cart service.",
    observations: [
      "The Cart service records an error indicating that it cannot connect to its storage backend.",
      "Traces capture failed `EmptyCart` operations involving Checkout and Cart, although the available boundary observations cannot establish precise attribution.",
      "Other observed calls to the Valkey backend do not report operation errors.",
      "The Cart container remains running and ready despite the storage connection problem.",
    ],
    investigation: "Determine whether a storage connection failure explains the affected EmptyCart operations, while distinguishing failed requests from other Cart operations that remain functional.",
  },
  "dependency-unavailable-01": {
    title: "Payment Dependency Unavailable",
    description: "Checkout cannot reliably reach the Payment service, preventing some customers from completing their orders.",
    cause: "Checkout attempts to send payment requests through an invalid service endpoint. As a result, communication with the Payment dependency fails and payment-dependent Checkout operations cannot complete normally.",
    observations: [
      "Checkout reports `UNAVAILABLE` status information for calls to Payment's `Charge` operation.",
      "The selected traces record errors in Checkout's payment calls and related `PlaceOrder` operations.",
      "Messages indicating successful payment completion are present in the baseline window but absent from the incident window.",
      "The Checkout container remains running and ready, even though payment-dependent requests are failing.",
    ],
    investigation: "Determine why Checkout cannot complete calls to Payment and explain how those dependency failures affect order processing.",
  },
  "downstream-latency-01": {
    title: "Shipping Slowdown",
    description: "Some shipping requests take much longer to complete, increasing the time Checkout spends waiting for Shipping.",
    cause: "The Shipping service experiences unusually long processing delays for some `ship-order` requests. These slow requests also increase the time spent on the Checkout-to-Shipping dependency path.",
    observations: [
      "The average duration of Shipping's `ship-order` operation increases substantially, although its median duration rises much less.",
      "The average latency of calls from Checkout to Shipping also increases significantly.",
      "Shipping's `get-quote` operation shows only a comparatively small latency change.",
      "The selected traces report no operation errors, and the Shipping container remains running.",
    ],
    investigation: "Identify the slow Shipping operation, distinguish it from operations that remain relatively stable, and evaluate its impact on Checkout.",
  },
  "memory-leak-01": {
    title: "Email Service Memory Growth",
    description: "The Email service consumes more memory and takes longer to process email requests.",
    cause: "The Email service experiences increased memory demand while processing email workloads. Memory consumption rises as the service handles requests, reducing the amount of available container memory.",
    observations: [
      "The Email container's reported memory usage increases compared with the baseline window.",
      "The amount of available container memory decreases as memory consumption grows.",
      "The average and median durations of `send_email` operations both increase substantially.",
      "The Email container remains running and ready, and the selected traces report no operation errors.",
    ],
    investigation: "Examine the relationship between increased memory consumption and slower email processing, without assuming that the available evidence proves a persistent memory leak.",
  },
  "messaging-failure-01": {
    title: "Order Messaging Slowdown",
    description: "Checkout takes longer to publish order messages while the Fraud Detection consumer experiences interruptions in its normal polling activity.",
    cause: "The order-messaging workflow experiences additional processing delays. The Fraud Detection consumer pauses during message processing, while Checkout's order-publishing path is also affected by additional queue-related work.",
    observations: [
      "The Fraud Detection consumer spends more time without polling Kafka for new records.",
      "Fraud Detection logs repeatedly report a one-second processing pause during the incident.",
      "Checkout's `publish orders` operation becomes slower.",
      "The recorded Kafka consumer lag remains at zero, so the selected metrics do not demonstrate a growing backlog of unconsumed records.",
      "The Fraud Detection and Kafka containers remain running and ready.",
    ],
    investigation: "Examine the changes in consumer polling and order publishing, and determine what the available evidence can explain without assuming that Kafka consumer lag increased.",
  },
  "crash-loop-backoff-01": {
    title: "Container Restart Loop",
    description: "A Telemetry Docs container repeatedly terminates instead of staying healthy and ready.",
    cause: "The container is configured to execute a command that exits with status code `42`. Because the main process terminates, Kubernetes repeatedly attempts to restart the container and applies restart backoff.",
    observations: [
      "Kubernetes records the container in a terminated state with exit code `42`.",
      "The container is not ready, and its recorded restart count has reached three.",
      "Kubernetes reports BackOff events while delaying repeated restart attempts.",
      "Restart-related metrics also record container restarts during the incident.",
    ],
    investigation: "Explain the repeated container terminations and Kubernetes restart backoff using the termination status, exit code, restart count, and events.",
  },
}

test("all nine scenario overviews contain the exact finalized content", () => {
  expect(Object.keys(scenarioOverviews).sort()).toEqual(Object.keys(finalized).sort())
  for (const [id, expected] of Object.entries(finalized)) {
    const { title, description, cause, observations, investigation } = scenarioOverviews[id]
    expect({ title, description, cause, observations, investigation }, id).toEqual(expected)
  }
})
