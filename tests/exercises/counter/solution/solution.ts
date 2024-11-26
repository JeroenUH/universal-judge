class Counter {
    private count: number;

    constructor() {
      this.count = 0;
    }

    add() {
        this.count++;
        return this;
    }

    get() {
        return this.count;
    }
}
