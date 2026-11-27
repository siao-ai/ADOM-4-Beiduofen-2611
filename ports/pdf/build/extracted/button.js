// ADOM-4-Beiduofen-2611: inference button
if (typeof ADOM5 === "undefined") {
  app.alert("ADOM engine not loaded: please enable JavaScript for this document.");
} else {
  try {
    var t0 = new Date().getTime();
    var r = ADOM5.chat(this.getField("prompt").valueAsString);
    var ms = new Date().getTime() - t0;
    this.getField("answer").value = r.text;
    this.getField("meta").value = "route=" + r.route + "; hit=" + r.hit + "; ms=" + ms + "; key=" + r.key;
  } catch (e) {
    app.alert("ADOM inference error: " + e);
  }
}
